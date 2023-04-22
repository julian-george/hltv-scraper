import pymongo
import numpy as np
import pandas as pd
from datetime import timedelta

client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["scraped-hltv"]
maps = db["maps"]
matches = db["matches"]
events = db["events"]
players = db["players"]

month_delta = timedelta(days=1) * 30

# These are the most common active duty maps, and the map_vector effectively creates a multi-classifier based on these
map_list = [
    "Ancient",
    "Anubis",
    "Cache",
    "Cobblestone",
    "Dust2",
    "Inferno",
    "Mirage",
    "Nuke",
    "Overpass",
    "Train",
    "Vertigo",
]


def get_map_vector(map_name):
    map_vector = []
    for name in map_list:
        # using `in` catches cases like the old _se maps, which are structurally similar enough to be considered the same
        #  consider appending a 0.5 or something if it's not exactly the same map
        if map_name in name:
            map_vector.append(1)
        else:
            map_vector.append(0)
    return map_vector


# amount of time before a map that duel amounts will be accumulated
duel_map_threshold = 18 * month_delta

# max observed team ranking. keep an eye on match rankings to see if any ever approach this
#  as of 4/7/23, max observed ranking is 404
max_ranking = 500

min_date = maps.find({"date": {"$ne": None}}).sort("date").limit(1).next()["date"]


def get_duels(team_one_ids, team_two_ids, date, performances):
    # there are 50 duels, one 5x5 with one side's kills, one 5x5 with the other side's kills
    duel_list = list(np.zeros((len(team_one_ids) * len(team_two_ids) * 2)))
    absolute_duel_threshold = date - duel_map_threshold
    for performance in performances:
        if performance["date"] < absolute_duel_threshold:
            continue
        duel_idx = 0
        # if non-all duels desired, wrap this in another for loop that goes thru "all", "fk", "awp", etc
        for player_id in team_one_ids:
            for opponent_id in team_two_ids:
                curr_duel_num = 0
                if player_id in performance["teamOneStats"]:
                    if (
                        opponent_id
                        in performance["teamOneStats"][player_id]["duelMap"]["all"]
                    ):
                        curr_duel_num += performance["teamOneStats"][player_id][
                            "duelMap"
                        ]["all"][opponent_id]
                elif player_id in performance["teamTwoStats"]:
                    if (
                        opponent_id
                        in performance["teamTwoStats"][player_id]["duelMap"]["all"]
                    ):
                        curr_duel_num += performance["teamTwoStats"][player_id][
                            "duelMap"
                        ]["all"][opponent_id]
                duel_list[duel_idx] += curr_duel_num
                duel_idx += 1

        for player_id in team_two_ids:
            for opponent_id in team_one_ids:
                curr_duel_num = 0
                if player_id in performance["teamOneStats"]:
                    if (
                        opponent_id
                        in performance["teamOneStats"][player_id]["duelMap"]["all"]
                    ):
                        curr_duel_num += performance["teamOneStats"][player_id][
                            "duelMap"
                        ]["all"][opponent_id]
                elif player_id in performance["teamTwoStats"]:
                    if (
                        opponent_id
                        in performance["teamTwoStats"][player_id]["duelMap"]["all"]
                    ):
                        curr_duel_num += performance["teamTwoStats"][player_id][
                            "duelMap"
                        ]["all"][opponent_id]
                duel_list[duel_idx] += curr_duel_num
                duel_idx += 1

    return duel_list


# amount of time before a map that rating avg and stdev will be compiled

short_term_threshold = 2 * month_delta

medium_term_threshold = 4 * month_delta

long_term_threshold = 12 * month_delta

map_rating_threshold = 5 * month_delta


def get_avg_winrates(
    team_one_ids,
    team_two_ids,
    date,
    performances,
    map_name=None,
    threshold=map_rating_threshold,
):
    team_one_win_num = [0 for i in range(len(team_one_ids))]
    team_one_played_num = [0 for i in range(len(team_one_ids))]

    team_two_win_num = [0 for i in range(len(team_two_ids))]
    team_two_played_num = [0 for i in range(len(team_two_ids))]
    for performance in performances:
        if performance["date"] >= date - threshold and (
            map_name == None or performance["mapType"] == map_name
        ):
            player_idx = 0
            for player_id_one in team_one_ids:
                if player_id_one in performance["teamOneStats"]:
                    team_one_win_num[player_idx] += 1
                    team_one_played_num[player_idx] += 1
                elif player_id_one in performance["teamTwoStats"]:
                    team_one_played_num[player_idx] += 1
                player_idx += 1
            player_idx = 0
            for player_id_two in team_two_ids:
                if player_id_two in performance["teamOneStats"]:
                    team_two_win_num[player_idx] += 1
                    team_two_played_num[player_idx] += 1
                elif player_id_two in performance["teamTwoStats"]:
                    team_two_played_num[player_idx] += 1
                player_idx += 1

    return [
        np.mean(team_one_win_num),
        np.mean(team_one_played_num),
        np.mean(team_two_win_num),
        np.mean(team_two_played_num),
    ]


# may not be necessary anymore
def filter_stats(stat_array):
    stat_array = list(
        filter(lambda stat: stat != "nan" and not np.isnan(stat), stat_array)
    )
    if len(stat_array) == 0:
        stat_array = [0]
    return stat_array


# added to feature vector if, when calculating mean rating, no rating datapoints were found
default_rating = 0.5


def get_map_stats(
    team_one_ids,
    team_two_ids,
    date,
    performances,
    map_name,
    thresholds=(map_rating_threshold),
):
    # multidimensional list with these levels:
    # (1 + # given ones)x thresholds
    #   10x players
    #     2x t side and ct side
    #       (# applicable performances)x ratings
    # With 3 thresholds, its a 4x10x2xn list (with each threshold & player having a different n)
    results = [
        [[[], []] for x2 in range(len(team_one_ids + team_two_ids))]
        for x1 in range(len(thresholds) + 1)
    ]

    num_valid = [
        [0 for x2 in range(len(team_one_ids + team_two_ids))]
        for x1 in range(len(thresholds) + 1)
    ]

    absolute_thresholds = tuple(map(lambda thresh: date - thresh, thresholds))
    map_absolute_threshold = date - map_rating_threshold

    for performance in performances:
        player_index = 0
        for player_id in team_one_ids + team_two_ids:
            ct_rating = None
            t_rating = None
            if player_id in performance["teamOneStats"]:
                ct_rating = performance["teamOneStats"][player_id]["ctStats"]["rating"]
                t_rating = performance["teamOneStats"][player_id]["tStats"]["rating"]
            elif player_id in performance["teamTwoStats"]:
                ct_rating = performance["teamTwoStats"][player_id]["ctStats"]["rating"]
                t_rating = performance["teamTwoStats"][player_id]["tStats"]["rating"]
            if not (not ct_rating or not t_rating):
                if (
                    performance["date"] <= map_absolute_threshold
                    and performance["mapType"] == map_name
                ):
                    results[0][player_index][0].append(ct_rating)
                    results[0][player_index][1].append(t_rating)
                    num_valid[0][player_index] += 1
                for i in range(len(absolute_thresholds)):
                    if performance["date"] <= absolute_thresholds[i]:
                        results[i + 1][player_index][0].append(ct_rating)
                        results[i + 1][player_index][1].append(t_rating)
                        num_valid[i + 1][player_index] += 1
            player_index += 1

    # returned list of parameters to be stored in the parameter matrix
    param_list = []

    for i in range(len(thresholds) + 1):
        for p in range(len(team_one_ids + team_two_ids)):
            param_list.append(num_valid[i][p])
            [ct_ratings, t_ratings] = results[i][p]
            param_list += (
                [np.mean(ct_ratings), np.std(ct_ratings)]
                if len(ct_ratings) > 0
                else [default_rating, 0]
            )
            param_list += (
                [np.mean(t_ratings), np.std(t_ratings)]
                if len(t_ratings) > 0
                else [default_rating, 0]
            )

    return param_list


detailed_threshold = long_term_threshold


def get_detailed_stats(team_one_ids, team_two_ids, date, performances):
    detailed_stats = [[[], []] for x in range(len(team_one_ids + team_two_ids))]

    num_valid = [0 for x in range(len(team_one_ids + team_two_ids))]

    detailed_absolute_threshold = date - detailed_threshold
    for performance in performances:
        if performance["date"] < detailed_absolute_threshold:
            continue
        player_index = 0
        for player_id in team_one_ids + team_two_ids:
            if player_id in performance["teamOneStats"]:
                detailed_stats[player_index][0].append(
                    performance["teamOneStats"][player_id]["ctStats"]
                )
                detailed_stats[player_index][1].append(
                    performance["teamOneStats"][player_id]["tStats"]
                )

            elif player_id in performance["teamTwoStats"]:
                detailed_stats[player_index][0].append(
                    performance["teamTwoStats"][player_id]["ctStats"]
                )
                detailed_stats[player_index][1].append(
                    performance["teamTwoStats"][player_id]["tStats"]
                )
            num_valid[player_index] += 1
            player_index += 1

    stats_list = []
    for i in range(len(detailed_stats)):
        player_stats = detailed_stats[i]
        # TODO: add mongo migration to handle NaN values in performances
        ct_stats = pd.DataFrame(player_stats[0]).to_dict(orient="list")
        t_stats = pd.DataFrame(player_stats[1]).to_dict(orient="list")

        ct_stats_analyzed = (
            [
                np.mean(filter_stats(ct_stats["kills"])),
                np.std(filter_stats(ct_stats["kills"])),
                np.mean(filter_stats(ct_stats["hsKills"])),
                np.std(filter_stats(ct_stats["hsKills"])),
                np.mean(filter_stats(ct_stats["assists"])),
                np.std(filter_stats(ct_stats["assists"])),
                np.mean(filter_stats(ct_stats["deaths"])),
                np.std(filter_stats(ct_stats["deaths"])),
                np.mean(filter_stats(ct_stats["kast"])),
                np.std(filter_stats(ct_stats["kast"])),
                np.mean(filter_stats(ct_stats["adr"])),
                np.std(filter_stats(ct_stats["adr"])),
                np.mean(filter_stats(ct_stats["fkDiff"])),
                np.std(filter_stats(ct_stats["fkDiff"])),
            ]
            if len(ct_stats) == 10
            else list(np.zeros(14))
        )
        t_stats_analyzed = (
            [
                np.mean(filter_stats(t_stats["kills"])),
                np.std(filter_stats(t_stats["kills"])),
                np.mean(filter_stats(t_stats["hsKills"])),
                np.std(filter_stats(t_stats["hsKills"])),
                np.mean(filter_stats(t_stats["assists"])),
                np.std(filter_stats(t_stats["assists"])),
                # add flash assists??
                np.mean(filter_stats(t_stats["deaths"])),
                np.std(filter_stats(t_stats["deaths"])),
                np.mean(filter_stats(t_stats["kast"])),
                np.std(filter_stats(t_stats["kast"])),
                np.mean(filter_stats(t_stats["adr"])),
                np.std(filter_stats(t_stats["adr"])),
                np.mean(filter_stats(t_stats["fkDiff"])),
                np.std(filter_stats(t_stats["fkDiff"])),
            ]
            if len(t_stats) == 10
            else list(np.zeros(14))
        )
        stats_list.append(num_valid[i])
        stats_list += ct_stats_analyzed
        stats_list += t_stats_analyzed
    return stats_list


def get_event_stats(team_one_ids, team_two_ids, event_id, performances):
    team_one_ratings = [([], []) for i in team_one_ids]
    team_one_win_num = [0 for i in team_one_ids]
    team_one_played_num = [0 for i in team_one_ids]

    team_two_ratings = [([], []) for i in team_two_ids]
    team_two_win_num = [0 for i in team_two_ids]
    team_two_played_num = [0 for i in team_two_ids]

    for performance in performances:
        if performance["match"][0]["eventId"] == event_id:
            player_idx = 0
            for player_id_one in team_one_ids:
                player_stats = None
                if player_id_one in performance["teamOneStats"]:
                    team_one_win_num[player_idx] += 1
                    team_one_played_num[player_idx] += 1
                    player_stats = performance["teamOneStats"][player_id_one]
                elif player_id_one in performance["teamTwoStats"]:
                    team_one_played_num[player_idx] += 1
                    player_stats = performance["teamTwoStats"][player_id_one]
                if player_stats != None:
                    team_one_ratings[player_idx][0].append(
                        player_stats["ctStats"]["rating"]
                    )
                    team_one_ratings[player_idx][1].append(
                        player_stats["tStats"]["rating"]
                    )
                player_idx += 1
            player_idx = 0
            for player_id_two in team_two_ids:
                player_stats = None
                if player_id_two in performance["teamOneStats"]:
                    team_two_win_num[player_idx] += 1
                    team_two_played_num[player_idx] += 1
                    player_stats = performance["teamOneStats"][player_id_two]
                elif player_id_two in performance["teamTwoStats"]:
                    team_two_played_num[player_idx] += 1
                    player_stats = performance["teamTwoStats"][player_id_two]
                if player_stats != None:
                    team_two_ratings[player_idx][0].append(
                        player_stats["ctStats"]["rating"]
                    )
                    team_two_ratings[player_idx][1].append(
                        player_stats["tStats"]["rating"]
                    )
                player_idx += 1

    event_stats_vector = []
    for rating_tuple in team_one_ratings + team_two_ratings:
        event_stats_vector.append(
            np.mean(rating_tuple[0]) if len(rating_tuple[0]) > 0 else default_rating
        )
        event_stats_vector.append(
            np.mean(rating_tuple[1]) if len(rating_tuple[1]) > 0 else default_rating
        )
    event_stats_vector += [np.mean(team_one_win_num), np.mean(team_one_played_num)]
    event_stats_vector += [np.mean(team_two_win_num), np.mean(team_two_played_num)]
    return event_stats_vector


def get_matchup_stats(
    team_one_ids, team_two_ids, date, performances, threshold=medium_term_threshold
):
    team_one_ratings = [([], []) for i in team_one_ids]
    team_two_ratings = [([], []) for i in team_two_ids]
    team_one_win_num = 0
    matchup_played_num = 0
    for performance in performances:
        if performance["date"] >= date - threshold:
            team_one_one_intersection = len(
                [id for id in team_one_ids if id in performance["teamOneStats"]]
            )
            team_two_two_intersection = len(
                [id for id in team_two_ids if id in performance["teamTwoStats"]]
            )
            team_one_two_intersection = len(
                [id for id in team_one_ids if id in performance["teamTwoStats"]]
            )
            team_two_one_intersection = len(
                [id for id in team_two_ids if id in performance["teamOneStats"]]
            )
            # essentially true if the given team_one is the winner of this performance
            order_match = (
                team_one_one_intersection >= 3 and team_two_two_intersection >= 3
            )
            if order_match or (
                team_one_two_intersection >= 3 and team_two_one_intersection >= 3
            ):
                if order_match:
                    team_one_win_num += 1
                matchup_played_num += 1
                player_idx = 0
                for player_id_one in team_one_ids:
                    stats_key = "teamOneStats" if order_match else "teamTwoStats"
                    if player_id_one in performance[stats_key]:
                        player_stats = performance[stats_key][player_id_one]
                        team_one_ratings[player_idx][0].append(
                            player_stats["ctStats"]["rating"]
                        )
                        team_one_ratings[player_idx][1].append(
                            player_stats["tStats"]["rating"]
                        )
                    player_idx += 1
                player_idx = 0
                for player_id_two in team_two_ids:
                    stats_key = "teamTwoStats" if order_match else "teamOneStats"
                    if player_id_two in performance[stats_key]:
                        player_stats = performance[stats_key][player_id_two]
                        team_two_ratings[player_idx][0].append(
                            player_stats["ctStats"]["rating"]
                        )
                        team_two_ratings[player_idx][1].append(
                            player_stats["tStats"]["rating"]
                        )
                    player_idx += 1
    matchup_stats_vector = []
    for rating_tuple in team_one_ratings + team_two_ratings:
        matchup_stats_vector.append(
            np.mean(rating_tuple[0]) if len(rating_tuple[0]) > 0 else default_rating
        )
        matchup_stats_vector.append(
            np.mean(rating_tuple[1]) if len(rating_tuple[1]) > 0 else default_rating
        )
    matchup_stats_vector.append(team_one_win_num)
    matchup_stats_vector.append(matchup_played_num)
    return matchup_stats_vector


def process_maps(maps_to_process, matrix_lock, history_lock, feature_data):
    local_history = set()
    for curr_map in maps_to_process:
        if feature_data.history is None:
            if curr_map["hltvId"] in local_history:
                continue
        else:
            with history_lock:
                if curr_map["hltvId"] in feature_data.history:
                    continue
        print("Processing map ID:", curr_map["hltvId"])
        winner = np.round(np.random.rand(1)[0])
        w = []
        related_match = curr_map["match"][0]
        raw_date = related_match["date"]
        # datetime rounded to the minute
        date = np.round((raw_date.timestamp() - min_date.timestamp()) / 360000, 5)
        # i-0
        w.append(date)
        # e.g bo1, bo3, etc
        format = related_match["numMaps"]
        # i-1
        w.append(format)

        related_event = curr_map["event"][0]
        # prizepool of event
        #  possibly too inconsistent to be useful, consider removing
        prizepool = related_event["prizePool"] or 0
        # i-2
        w.append(prizepool)
        # if event is online
        online = int(related_event["online"])
        # i-3
        w.append(online)
        # number of teams in event
        team_num = related_event["teamNum"]
        team_rankings = np.array(
            list(
                map(
                    # normalizes rankings by subtracting them by max observed ranking and turning to 0 if it's null
                    lambda ranking: max_ranking - ranking if ranking != None else 0,
                    related_event["teamRankings"],
                )
            )
        )
        # mean and stdev of team rankings at event
        team_rankings_analyzed = [np.mean(team_rankings), np.std(team_rankings)]
        # i-[4,5]
        w += team_rankings_analyzed

        ranking_one = (
            max_ranking - curr_map["teamOneRanking"]
            if curr_map["teamOneRanking"] != None
            else 0
        )
        ranking_two = (
            max_ranking - curr_map["teamTwoRanking"]
            if curr_map["teamTwoRanking"] != None
            else 0
        )
        # i-[6,7]
        if winner == 1:
            w += [ranking_one, ranking_two]
        else:
            w += [ranking_two, ranking_one]

        map_name = curr_map["mapType"]
        # series of binary params (multi-classifier) denoting which map is being played
        map_vector = get_map_vector(map_name)
        # i-[8,18]
        w += map_vector

        team_one_ids = list(
            curr_map["teamOneStats" if winner == 1 else "teamTwoStats"].keys()
        )
        team_two_ids = list(
            curr_map["teamTwoStats" if winner == 1 else "teamOneStats"].keys()
        )
        # skip this map if there were more than 5 players per team playing (ie weird substitution/connectivity stuff).
        #   the number of those maps is low so it cuts out outliers while also keeping param vector the same length
        if len(team_one_ids) != 5 or len(team_two_ids) != 5:
            continue

        # this assumes that long_term_threshold is longer than all the others
        performances = list(
            maps.aggregate(
                [
                    {
                        "$lookup": {
                            "from": "matches",
                            "localField": "matchId",
                            "foreignField": "hltvId",
                            "as": "match",
                        }
                    },
                    # {
                    #     "$lookup": {
                    #         "from": "events",
                    #         "localField": "match.0.eventId",
                    #         "foreignField": "hltvId",
                    #         "as": "event",
                    #     }
                    # },
                    {
                        "$match": {
                            "$and": [
                                {"date": {"$lt": raw_date}},
                                {"date": {"$gte": raw_date - long_term_threshold}},
                                {"players": {"$in": team_one_ids + team_two_ids}},
                            ]
                        }
                    },
                    {"$sort": {"date": -1}},
                ]
            )
        )

        # calculating duel maps for all of them
        duels = get_duels(team_one_ids, team_two_ids, raw_date, performances)
        # i-[19,68]
        w += duels
        # i-[69,72]
        win_rates = get_avg_winrates(
            team_one_ids,
            team_two_ids,
            raw_date,
            performances,
            None,
            short_term_threshold,
        )
        # i-[73,76]
        w += win_rates
        map_win_rates = get_avg_winrates(
            team_one_ids,
            team_two_ids,
            raw_date,
            performances,
            map_name,
            map_rating_threshold,
        )
        w += map_win_rates
        # big (280-length) array containing mean and stdev of almost all collected stats
        # within this function and subsequent ones, important to put ct stats before t stats
        stats_list = get_map_stats(
            team_one_ids,
            team_two_ids,
            raw_date,
            performances,
            map_name=map_name,
            thresholds=(
                short_term_threshold,
                medium_term_threshold,
                long_term_threshold,
            ),
        )
        # map: i-[77,126]
        # short_term: i-[127,176]
        # medium_term: i-[177,226]
        # long_term: i-[227,276]
        w += stats_list
        detailed_stats = get_detailed_stats(
            team_one_ids, team_two_ids, raw_date, performances
        )
        # i-[277,566]
        w += detailed_stats

        # avg ratings and maps won/played for this event
        event_stats = get_event_stats(
            team_one_ids, team_two_ids, related_match["eventId"], performances
        )

        # i-[567,590]
        w += event_stats

        # avg player ratings when these teams have played, times team one has won, and times they have played
        matchup_stats = get_matchup_stats(
            team_one_ids, team_two_ids, raw_date, performances
        )
        # i-[591,612]
        w += matchup_stats

        # i-613
        w.append(winner)

        # map scores - to be taken out when needed during training/testing
        teamOneKey = "teamOne" if winner == 1 else "teamTwo"
        # i-[614,616]
        w.append(curr_map["score"][teamOneKey]["ct"])
        w.append(curr_map["score"][teamOneKey]["t"])
        w.append(curr_map["score"][teamOneKey]["ot"])

        teamTwoKey = "teamTwo" if winner == 1 else "teamOne"
        # i-[617,619]
        w.append(curr_map["score"][teamTwoKey]["ct"])
        w.append(curr_map["score"][teamTwoKey]["t"])
        w.append(curr_map["score"][teamTwoKey]["ot"])

        # these are just used for inspecting processed data, so we can find their sources. clipped out during training
        # i-620
        w.append(curr_map["hltvId"])
        # i-621
        w.append(related_match["hltvId"])

        # print(w)

        if feature_data.history is None:
            local_history.add(curr_map["hltvId"])
        else:
            with history_lock:
                feature_data.history.add(curr_map["hltvId"])

        with matrix_lock:
            feature_data.matrix = np.append(
                feature_data.matrix, np.array([w]).T, axis=1
            )

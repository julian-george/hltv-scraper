import pymongo
import os
import numpy as np
import pandas as pd
from datetime import timedelta

num_pools = 80


client = pymongo.MongoClient(
    os.environ["MONGODB_URI"], maxPoolSize=num_pools + 8, minPoolSize=num_pools
)
print("Helper client connected")
db = client["scraped-hltv"]
maps = db["maps"]
matches = db["matches"]
events = db["events"]
players = db["players"]


month_delta = timedelta(days=1) * 30

team_prefixes = ["team_one", "team_two"]

game_sides = ["ct", "t"]

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
    map_dict = {f"map_{name.lower()}_bool": map_name in name for name in map_list}
    return map_dict


# amount of time before a map that duel amounts will be accumulated
duel_map_threshold = 18 * month_delta

# max observed team ranking. keep an eye on match rankings to see if any ever approach this
#  as of 4/7/23, max observed ranking is 404
max_ranking = 500

min_date = maps.find({"date": {"$ne": None}}).sort("date").limit(1).next()["date"]


# @profile
def get_duels(team_one_ids, team_two_ids, date, performances):
    duel_obj = {
        f"duel_{pref}_{i}_{j}": 0
        for i in range(5)
        for j in range(5)
        for pref in team_prefixes
    }
    absolute_duel_threshold = date - duel_map_threshold
    for performance in performances:
        if performance["date"] < absolute_duel_threshold:
            continue
        player_idx = 0
        # if non-all duels desired, wrap this in another for loop that goes thru "all", "fk", "awp", etc
        for player_id in team_one_ids:
            opponent_idx = 0
            for opponent_id in team_two_ids:
                curr_duel_num = 0
                if player_id in performance["teamOneStats"]:
                    if (
                        opponent_id
                        in performance["teamOneStats"][player_id]["duelMap"]["all"]
                    ):
                        curr_duel_num = performance["teamOneStats"][player_id][
                            "duelMap"
                        ]["all"][opponent_id]
                elif player_id in performance["teamTwoStats"]:
                    if (
                        opponent_id
                        in performance["teamTwoStats"][player_id]["duelMap"]["all"]
                    ):
                        curr_duel_num = performance["teamTwoStats"][player_id][
                            "duelMap"
                        ]["all"][opponent_id]
                duel_obj[f"duel_team_one_{player_idx}_{opponent_idx}"] += curr_duel_num
                opponent_idx += 1
            player_idx += 1

        player_idx = 0
        for player_id in team_two_ids:
            opponent_idx = 0
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
                duel_obj[f"duel_team_two_{player_idx}_{opponent_idx}"] += curr_duel_num
                opponent_idx += 1
            player_idx += 1

    return duel_obj


# amount of time before a map that rating avg and stdev will be compiled

short_term_threshold = 2 * month_delta

medium_term_threshold = 4 * month_delta

long_term_threshold = 12 * month_delta

map_rating_threshold = 5 * month_delta


# @profile
def get_avg_winrates(
    team_one_ids,
    team_two_ids,
    date,
    performances,
    map_name=None,
    threshold=map_rating_threshold,
    suffix="overall",
):
    # team_one_ratings = [([], []) for i in team_one_ids]
    team_one_win_num = [0 for i in team_one_ids]
    team_one_played_num = [0 for i in team_one_ids]
    team_one_rounds = [[] for i in team_one_ids]

    # team_two_ratings = [([], []) for i in team_two_ids]
    team_two_win_num = [0 for i in team_two_ids]
    team_two_played_num = [0 for i in team_two_ids]
    team_two_rounds = [[] for i in team_two_ids]
    for performance in performances:
        if performance["date"] >= date - threshold and (
            map_name == None or performance["mapType"] == map_name
        ):
            player_idx = 0
            for player_id_one in team_one_ids:
                score_key = None
                if player_id_one in performance["teamOneStats"]:
                    team_one_win_num[player_idx] += 1
                    team_one_played_num[player_idx] += 1
                    score_key = "teamOne"
                elif player_id_one in performance["teamTwoStats"]:
                    team_one_played_num[player_idx] += 1
                    score_key = "teamTwo"
                if score_key:
                    team_one_rounds[player_idx].append(
                        performance["score"][score_key]["ct"]
                        + performance["score"][score_key]["t"]
                    )
                # stats_key = score_key + "Stats"
                # stats_obj = performance[stats_key][player_id_one]
                # team_one_ratings[player_idx][0].append(stats_obj["ctStats"]["rating"])
                # team_one_ratings[player_idx][1].append(stats_obj["tStats"]["rating"])
                player_idx += 1
            player_idx = 0
            for player_id_two in team_two_ids:
                score_key = None
                if player_id_two in performance["teamOneStats"]:
                    team_two_win_num[player_idx] += 1
                    team_two_played_num[player_idx] += 1
                    score_key = "teamOne"
                elif player_id_two in performance["teamTwoStats"]:
                    team_two_played_num[player_idx] += 1
                    score_key = "teamTwo"
                if score_key:
                    team_two_rounds[player_idx].append(
                        performance["score"][score_key]["ct"]
                        + performance["score"][score_key]["t"]
                    )
                # stats_key = score_key + "Stats"
                # stats_obj = performance[stats_key][player_id_two]
                # team_two_ratings[player_idx][0].append(stats_obj["ctStats"]["rating"])
                # team_two_ratings[player_idx][1].append(stats_obj["tStats"]["rating"])
                player_idx += 1

    # team_one_ratings_vector = []
    # for ratings_tuple in team_one_ratings:
    #     team_one_ratings_vector.append(
    #         np.mean(ratings_tuple[0]) if len(ratings_tuple[0]) > 0 else default_rating
    #     )
    #     team_one_ratings_vector.append(
    #         np.mean(ratings_tuple[1]) if len(ratings_tuple[1]) > 0 else default_rating
    #     )

    # team_two_ratings_vector = []
    # for ratings_tuple in team_two_ratings:
    #     team_two_ratings_vector.append(
    #         np.mean(ratings_tuple[0]) if len(ratings_tuple[0]) > 0 else default_rating
    #     )
    #     team_two_ratings_vector.append(
    #         np.mean(ratings_tuple[1]) if len(ratings_tuple[1]) > 0 else default_rating
    #     )

    team_one_mean_rounds = [
        np.mean(player_rounds) if len(player_rounds) > 0 else default_rounds
        for player_rounds in team_one_rounds
    ]
    team_two_mean_rounds = [
        np.mean(player_rounds) if len(player_rounds) > 0 else default_rounds
        for player_rounds in team_two_rounds
    ]

    return {
        f"team_one_win_num_{suffix}": np.mean(team_one_win_num),
        f"team_one_played_num_{suffix}": np.mean(team_one_played_num),
        f"team_one_mean_rounds_{suffix}": np.mean(team_one_mean_rounds),
        f"team_two_win_num_{suffix}": np.mean(team_two_win_num),
        f"team_two_played_num_{suffix}": np.mean(team_two_played_num),
        f"team_two_mean_rounds_{suffix}": np.mean(team_two_mean_rounds),
    }


# added to feature vector if, when calculating mean rating, no rating datapoints were found
default_rating = 0.5

default_rounds = 4


# @profile
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
    # With 3 thresholds, its a 5x10x2xn list (with each threshold & player having a different n)
    results = [
        [[[], []] for x2 in range(len(team_one_ids + team_two_ids))]
        for x1 in range(len(thresholds) + 1)
    ]

    num_valid = [
        [0 for x2 in range(len(team_one_ids + team_two_ids))]
        for x1 in range(len(thresholds) + 1)
    ]

    threshold_names = ["short", "medium", "long", "map"]

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

    param_obj = {}

    for i in range(len(thresholds) + 1):
        for p in range(len(team_one_ids + team_two_ids)):
            pref = team_prefixes[0] if p < 5 else team_prefixes[1]
            player_idx = p % 5
            param_obj[
                f"{pref}_player_{player_idx}_maps_played_{threshold_names[i]}"
            ] = num_valid[i][p]
            [ct_ratings, t_ratings] = results[i][p]
            param_obj[
                f"{pref}_player_{player_idx}_ct_rating_avg_{threshold_names[i]}"
            ] = (np.mean(ct_ratings) if len(ct_ratings) > 0 else default_rating)
            param_obj[
                f"{pref}_player_{player_idx}_ct_rating_std_{threshold_names[i]}"
            ] = (np.std(ct_ratings) if len(ct_ratings) > 0 else 0)
            param_obj[
                f"{pref}_player_{player_idx}_t_rating_avg_{threshold_names[i]}"
            ] = (np.mean(t_ratings) if len(t_ratings) > 0 else default_rating)
            param_obj[
                f"{pref}_player_{player_idx}_t_rating_std_{threshold_names[i]}"
            ] = (np.std(t_ratings) if len(t_ratings) > 0 else 0)

    return param_obj


detailed_threshold = long_term_threshold

detailed_stats_keys = ["kills", "hsKills", "assists", "deaths", "kast", "adr", "fkDiff"]


# @profile
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

    stats_obj = {}
    for i in range(len(detailed_stats)):
        player_stats = detailed_stats[i]
        player_idx = i % 5
        pref = team_prefixes[0] if i < 5 else team_prefixes[1]
        ct_stats = pd.DataFrame(player_stats[0]).to_dict(orient="list")
        t_stats = pd.DataFrame(player_stats[1]).to_dict(orient="list")
        ct_stats_analyzed = {
            k: v
            for obj in (
                {
                    f"{pref}_player_{player_idx}_ct_{stat}_avg": np.mean(
                        ct_stats.get(stat, 0)
                    ),
                    f"{pref}_player_{player_idx}_ct_{stat}_std": np.std(
                        ct_stats.get(stat, 0)
                    ),
                }
                for stat in detailed_stats_keys
            )
            for k, v in obj.items()
        }
        t_stats_analyzed = {
            k: v
            for obj in (
                {
                    f"{pref}_player_{player_idx}_t_{stat}_avg": np.mean(
                        t_stats.get(stat, 0)
                    ),
                    f"{pref}_player_{player_idx}_t_{stat}_std": np.std(
                        t_stats.get(stat, 0)
                    ),
                }
                for stat in detailed_stats_keys
            )
            for k, v in obj.items()
        }
        stats_obj = (
            stats_obj
            | ct_stats_analyzed
            | t_stats_analyzed
            | {
                f"{pref}_player_{player_idx}_maps_played_detailed": num_valid[i],
            }
        )
    return stats_obj


# @profile
def get_event_stats(team_one_ids, team_two_ids, event_id, performances):
    team_one_ratings = [([], []) for i in team_one_ids]
    team_one_win_num = [0 for i in team_one_ids]
    team_one_played_num = [0 for i in team_one_ids]
    team_one_rounds = [[] for i in team_one_ids]

    team_two_ratings = [([], []) for i in team_two_ids]
    team_two_win_num = [0 for i in team_two_ids]
    team_two_played_num = [0 for i in team_two_ids]
    team_two_rounds = [[] for i in team_two_ids]

    for performance in performances:
        if performance["match"][0]["eventId"] == event_id:
            player_idx = 0
            for player_id_one in team_one_ids:
                score_key = None
                if player_id_one in performance["teamOneStats"]:
                    team_one_win_num[player_idx] += 1
                    team_one_played_num[player_idx] += 1
                    score_key = "teamOne"
                elif player_id_one in performance["teamTwoStats"]:
                    team_one_played_num[player_idx] += 1
                    score_key = "teamTwo"
                if score_key:
                    team_one_rounds[player_idx].append(
                        performance["score"][score_key]["ct"]
                        + performance["score"][score_key]["t"]
                    )
                    player_stats = performance[score_key + "Stats"][player_id_one]
                    team_one_ratings[player_idx][0].append(
                        player_stats["ctStats"]["rating"]
                    )
                    team_one_ratings[player_idx][1].append(
                        player_stats["tStats"]["rating"]
                    )
                player_idx += 1
            player_idx = 0
            for player_id_two in team_two_ids:
                score_key = None
                if player_id_two in performance["teamOneStats"]:
                    team_two_win_num[player_idx] += 1
                    team_two_played_num[player_idx] += 1
                    score_key = "teamOne"
                elif player_id_two in performance["teamTwoStats"]:
                    team_two_played_num[player_idx] += 1
                    score_key = "teamTwo"
                if score_key:
                    team_two_rounds[player_idx].append(
                        performance["score"][score_key]["ct"]
                        + performance["score"][score_key]["t"]
                    )
                    player_stats = performance[score_key + "Stats"][player_id_two]
                    team_two_ratings[player_idx][0].append(
                        player_stats["ctStats"]["rating"]
                    )
                    team_two_ratings[player_idx][1].append(
                        player_stats["tStats"]["rating"]
                    )
                player_idx += 1

    event_stats_obj = {}

    for i in range(len(team_one_ratings + team_two_ratings)):
        rating_tuple = (team_one_ratings + team_two_ratings)[i]
        player_idx = i % 5
        pref = team_prefixes[0] if i < 5 else team_prefixes[1]
        event_stats_obj[f"{pref}_player_{player_idx}_ct_rating_avg_event"] = (
            np.mean(rating_tuple[0]) if len(rating_tuple[0]) > 0 else default_rating
        )
        event_stats_obj[f"{pref}_player_{player_idx}_t_rating_avg_event"] = (
            np.mean(rating_tuple[1]) if len(rating_tuple[1]) > 0 else default_rating
        )

    team_one_mean_rounds = [
        np.mean(player_rounds) if len(player_rounds) > 0 else default_rounds
        for player_rounds in team_one_rounds
    ]
    team_two_mean_rounds = [
        np.mean(player_rounds) if len(player_rounds) > 0 else default_rounds
        for player_rounds in team_two_rounds
    ]

    event_stats_obj |= {
        "team_one_mean_rounds_event": np.mean(team_one_mean_rounds),
        "team_two_mean_rounds_event": np.mean(team_two_mean_rounds),
    }
    event_stats_obj |= {
        "team_one_win_num_event": np.mean(team_one_win_num),
        "team_two_win_num_event": np.mean(team_two_win_num),
    }
    event_stats_obj |= {
        "team_one_played_num_event": np.mean(team_one_played_num),
        "team_two_played_num_event": np.mean(team_two_played_num),
    }

    return event_stats_obj


# @profile
def get_matchup_stats(
    team_one_ids, team_two_ids, date, performances, threshold=medium_term_threshold
):
    team_one_ratings = [([], []) for i in team_one_ids]
    team_one_rounds = [[] for i in team_one_ids]
    team_two_ratings = [([], []) for i in team_two_ids]
    team_two_rounds = [[] for i in team_two_ids]
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
                    score_key = "teamOne" if order_match else "teamTwo"
                    stats_key = score_key + "Stats"
                    if player_id_one in performance[stats_key]:
                        player_stats = performance[stats_key][player_id_one]
                        team_one_ratings[player_idx][0].append(
                            player_stats["ctStats"]["rating"]
                        )
                        team_one_ratings[player_idx][1].append(
                            player_stats["tStats"]["rating"]
                        )
                        team_one_rounds[player_idx].append(
                            performance["score"][score_key]["ct"]
                            + performance["score"][score_key]["t"]
                        )
                    player_idx += 1
                player_idx = 0
                for player_id_two in team_two_ids:
                    score_key = "teamTwo" if order_match else "teamOne"
                    stats_key = score_key + "Stats"
                    if player_id_two in performance[stats_key]:
                        player_stats = performance[stats_key][player_id_two]
                        team_two_ratings[player_idx][0].append(
                            player_stats["ctStats"]["rating"]
                        )
                        team_two_ratings[player_idx][1].append(
                            player_stats["tStats"]["rating"]
                        )
                        team_two_rounds[player_idx].append(
                            performance["score"][score_key]["ct"]
                            + performance["score"][score_key]["t"]
                        )
                    player_idx += 1
    matchup_stats_obj = {}
    for i in range(len(team_one_ratings + team_two_ratings)):
        rating_tuple = (team_one_ratings + team_two_ratings)[i]
        player_idx = i % 5
        pref = team_prefixes[0] if i < 5 else team_prefixes[1]
        matchup_stats_obj[f"{pref}_player_{player_idx}_ct_rating_avg_matchup"] = (
            np.mean(rating_tuple[0]) if len(rating_tuple[0]) > 0 else default_rating
        )
        matchup_stats_obj[f"{pref}_player_{player_idx}_t_rating_avg_matchup"] = (
            np.mean(rating_tuple[1]) if len(rating_tuple[1]) > 0 else default_rating
        )

    team_one_mean_rounds = [
        np.mean(player_rounds) if len(player_rounds) > 0 else default_rounds
        for player_rounds in team_one_rounds
    ]
    team_two_mean_rounds = [
        np.mean(player_rounds) if len(player_rounds) > 0 else default_rounds
        for player_rounds in team_two_rounds
    ]

    matchup_stats_obj |= {
        "team_one_mean_rounds_matchup": np.mean(team_one_mean_rounds),
        "team_two_mean_rounds_matchup": np.mean(team_two_mean_rounds),
    }
    matchup_stats_obj["team_one_win_num_matchup"] = team_one_win_num
    matchup_stats_obj["teams_played_num_matchup"] = matchup_played_num
    return matchup_stats_obj


def generate_data_point(curr_map, played=True, map_type=None):
    winner = np.random.randint(2) if played else 1
    w = {}
    related_match = curr_map["match"][0] if played else None
    raw_date = related_match["date"] if related_match else curr_map["date"]
    # datetime rounded to the minute
    date = np.round((raw_date.timestamp() - min_date.timestamp()) / 360000, 5)
    # i-0
    w["map_date"] = date
    # e.g bo1, bo3, etc
    format = related_match["numMaps"] if played else curr_map["numMaps"]
    # i-1
    w["match_num_maps"] = format

    related_event = curr_map["event"][0]
    # prizepool of event
    #  possibly too inconsistent to be useful, consider removing
    prizepool = related_event["prizePool"] or 0
    # i-2
    w["event_prize_pool"] = prizepool
    # if event is online
    online = int(related_event["online"])
    # i-3
    w["online"] = online
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
    team_rankings_analyzed = {
        "event_team_rankings_mean": np.mean(team_rankings),
        "event_team_rankings_std": np.std(team_rankings),
    }
    # i-[4,5]
    w |= team_rankings_analyzed

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
    w["team_one_ranking"] = ranking_one if winner == 1 else ranking_two
    w["team_two_ranking"] = ranking_two if winner == 1 else ranking_one

    map_name = curr_map["mapType"] if "mapType" in curr_map else map_type
    # series of binary params (multi-classifier) denoting which map is being played
    map_vector = get_map_vector(map_name)
    # i-[8,18]
    w |= map_vector

    team_one_ids = (
        list(curr_map["teamOneStats" if winner == 1 else "teamTwoStats"].keys())
        if played
        else [str(pid) for pid in curr_map["players"]["firstTeam"]]
    )
    team_two_ids = (
        list(curr_map["teamTwoStats" if winner == 1 else "teamOneStats"].keys())
        if played
        else [str(pid) for pid in curr_map["players"]["secondTeam"]]
    )

    # skip this map if there were more than 5 players per team playing (ie weird substitution/connectivity stuff).
    #   the number of those maps is low so it cuts out outliers while also keeping param vector the same length
    if len(team_one_ids) != 5 or len(team_two_ids) != 5:
        return None

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
                {
                    "$lookup": {
                        "from": "events",
                        "localField": "match.0.eventId",
                        "foreignField": "hltvId",
                        "as": "event",
                    }
                },
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
    w |= duels
    # i-[69,74]
    win_rates = get_avg_winrates(
        team_one_ids,
        team_two_ids,
        raw_date,
        performances,
        None,
        short_term_threshold,
    )

    # i-[75,80]
    w |= win_rates
    map_win_rates = get_avg_winrates(
        team_one_ids,
        team_two_ids,
        raw_date,
        performances,
        map_name,
        map_rating_threshold,
        suffix="map",
    )
    w |= map_win_rates
    # big (200-length) array containing mean and stdev of almost all collected stats
    # within this function and subsequent ones, important to put ct stats before t stats
    threshold_stats = get_map_stats(
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
    # map: i-[81,130]
    # short_term: i-[131,180]
    # medium_term: i-[181,230]
    # long_term: i-[231,280]
    w |= threshold_stats
    detailed_stats = get_detailed_stats(
        team_one_ids, team_two_ids, raw_date, performances
    )
    # i-[281,570]
    w |= detailed_stats
    # avg ratings and maps won/played for this event
    event_stats = get_event_stats(
        team_one_ids,
        team_two_ids,
        related_match["eventId"] if played else curr_map["eventId"],
        performances,
    )

    # i-[571,596]
    w |= event_stats

    # avg player ratings when these teams have played, times team one has won, and times they have played
    matchup_stats = get_matchup_stats(
        team_one_ids, team_two_ids, raw_date, performances
    )
    # i-[597,620]
    w |= matchup_stats

    # handles ties
    if played:
        winner_score = (
            curr_map["score"]["teamOne"]["ct"]
            + curr_map["score"]["teamOne"]["t"]
            + curr_map["score"]["teamOne"]["ot"]
        )
        loser_score = (
            curr_map["score"]["teamTwo"]["ct"]
            + curr_map["score"]["teamTwo"]["t"]
            + curr_map["score"]["teamTwo"]["ot"]
        )
        if winner_score == loser_score:
            winner = 0.5
        # i-621
        w["winner"] = winner

        score_sides = ["ct", "t", "ot"]
        team_keys = ["teamOne", "teamTwo"] if winner == 1 else ["teamTwo", "teamOne"]
        pref_idx = 0
        # map scores - to be taken out when needed during training/testing
        for team_key in team_keys:
            for side in score_sides:
                w[f"{team_prefixes[pref_idx]}_score_{side}"] = curr_map["score"][
                    team_key
                ][side]
            pref_idx += 1

    # these are just used for inspecting processed data, so we can find their sources. clipped out during training
    # i-628
    w["map_id"] = curr_map["hltvId"]
    # i-629
    w["match_id"] = related_match["hltvId"] if related_match else None
    return w


# @profile
def process_maps(
    maps_to_process, frame_lock, history_lock, exit_lock, feature_data, thread_idx
):
    local_history = set()
    w_list = []
    print(f"New map processor started: [{thread_idx}]")
    for map_idx in range(len(maps_to_process)):
        curr_map = maps_to_process[map_idx]
        print(f"[{thread_idx}] Processing map ID:", curr_map["hltvId"])
        w = generate_data_point(curr_map)
        # with exit_lock:
        #     if feature_data.to_exit:
        #         return
        # if feature_data.history is None:
        #     if curr_map["hltvId"] in local_history:
        #         continue
        # else:
        #     with history_lock:
        #         if curr_map["hltvId"] in feature_data.history:
        #             continue

        # with exit_lock:
        #     if feature_data.to_exit:
        #         return

        if feature_data.history is None:
            local_history.add(curr_map["hltvId"])
        else:
            with history_lock:
                feature_data.history.add(curr_map["hltvId"])

        with frame_lock:
            feature_data.frame.loc[len(feature_data.frame.index)] = w
    print(f"[{thread_idx}] Done processing maps")

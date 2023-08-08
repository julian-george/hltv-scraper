import pymongo
import os
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import traceback
from datetime import timedelta
from tqdm import tqdm

load_dotenv()

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

max_threshold = 3 * month_delta


team_suffixes = ["team_one", "team_two"]

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


def quantize_timedelta(date):
    return np.round(date.total_seconds(), 5)


def quantize_time(date):
    return np.round(date.timestamp(), 5)


def get_map_vector(map_name):
    map_dict = {f"map_{name.lower()}_bool": map_name in name for name in map_list}
    return map_dict


# max observed team ranking. keep an eye on match rankings to see if any ever approach this
#  as of 4/7/23, max observed ranking is 404
max_ranking = 500


min_birth_year = (
    players.find({"birthYear": {"$ne": None}})
    .sort("birthYear")
    .limit(1)
    .next()["birthYear"]
)

matchup_category = "matchup"

# number of matches in a row a team needs to not play together to be marked as a roster change
apart_threshold = 6

default_rounds = 6
default_rating = 0.6
default_side_stat = 0.4
# default_duel_stat = 0
default_last = 0
default_birth_year = 2001
default_stdevs = {"round": 2.75, "rating": 0.4}
default_rating_variance = 0.45
default_side_winrate = 0.375


def generate_round_rating_stats(
    team_one_ids, team_two_ids, performances, condition_dict, raw_date
):
    category_stats_dict = {}
    individual_stats_dict = {}
    results_dict = {}
    sided_stats = ["kast", "rating", "fkDiff"]
    # duel_stats = ["awp", "firstKill"]
    for player_id in team_one_ids + team_two_ids:
        category_stats_dict[player_id] = {}
        individual_stats_dict[player_id] = {
            # "wonduels": 0,
            "twinrate": [default_side_winrate],
            "ctwinrate": [default_side_winrate],
            "otwinrate": [default_side_winrate],
        }
        for sided_stat in sided_stats:
            individual_stats_dict[player_id][sided_stat] = {
                "ct": [default_side_stat],
                "t": [default_side_stat],
            }
        # for duel_stat in duel_stats:
        #     individual_stats_dict[player_id][duel_stat] = [default_duel_stat]

        for category in condition_dict.keys():
            category_stats_dict[player_id][category] = {
                "round": {"ct": [default_rounds], "t": [default_rounds]},
                "rating": {"ct": [default_rating], "t": [default_rating]},
            }
    team_one_apart_maps = 0
    team_two_apart_maps = 0
    # add stats to list for each player
    for performance in performances:
        try:
            for i, player_id in enumerate(team_one_ids + team_two_ids):
                team_key = None
                away_key = None
                if player_id in performance["teamOneStats"].keys():
                    team_key = "teamOne"
                    away_key = "teamTwo"
                elif player_id in performance["teamTwoStats"].keys():
                    team_key = "teamTwo"
                    away_key = "teamOne"
                if team_key != None:
                    home_score = (
                        performance["score"][team_key]["ct"]
                        + performance["score"][team_key]["t"]
                        + performance["score"][team_key]["ot"]
                    )
                    away_score = (
                        performance["score"][away_key]["ct"]
                        + performance["score"][away_key]["t"]
                        + performance["score"][away_key]["ot"]
                    )
                    if player_id in team_one_ids:
                        if not "timetogether_team_one" in results_dict:
                            if (
                                intersection_length(
                                    team_one_ids, performance[f"{team_key}Stats"].keys()
                                )
                                != 5
                            ):
                                team_one_apart_maps += 1
                            else:
                                team_one_apart_maps = 0
                            if team_one_apart_maps >= apart_threshold:
                                results_dict[
                                    "timetogether_team_one"
                                ] = quantize_timedelta(raw_date - performance["date"])
                        if not "lastwin_team_one" in results_dict:
                            if home_score > away_score:
                                results_dict["lastwin_team_one"] = quantize_timedelta(
                                    raw_date - performance["date"]
                                )
                        if not "lastloss_team_one" in results_dict:
                            if away_score > home_score:
                                results_dict["lastloss_team_one"] = quantize_timedelta(
                                    raw_date - performance["date"]
                                )
                    elif player_id in team_two_ids:
                        if not "timetogether_team_two" in results_dict:
                            if (
                                intersection_length(
                                    team_two_ids, performance[f"{team_key}Stats"].keys()
                                )
                                != 5
                            ):
                                team_two_apart_maps += 1
                            else:
                                team_two_apart_maps = 0
                            if team_two_apart_maps >= apart_threshold:
                                results_dict[
                                    "timetogether_team_two"
                                ] = quantize_timedelta(raw_date - performance["date"])
                        if not "lastwin_team_two" in results_dict:
                            if home_score > away_score:
                                results_dict["lastwin_team_two"] = quantize_timedelta(
                                    raw_date - performance["date"]
                                )
                        if not "lastloss_team_two" in results_dict:
                            if away_score > home_score:
                                results_dict["lastloss_team_two"] = quantize_timedelta(
                                    raw_date - performance["date"]
                                )

                    for stat in sided_stats:
                        for side in game_sides:
                            individual_stats_dict[player_id][stat][side].append(
                                performance[f"{team_key}Stats"][player_id][
                                    f"{side}Stats"
                                ][stat]
                            )
                    # for stat in duel_stats:
                    #     individual_stats_dict[player_id][stat].append(
                    #         np.sum(
                    #             list(
                    #                 performance[f"{team_key}Stats"][player_id]["duelMap"][
                    #                     stat
                    #                 ].values()
                    #             )
                    #         )
                    #     )
                    # for opponent_id, wins in performance[f"{team_key}Stats"][player_id][
                    #     "duelMap"
                    # ]["all"].items():
                    #     if (
                    #         i <= 4
                    #         and opponent_id in team_two_ids
                    #         or i > 4
                    #         and opponent_id in team_one_ids
                    #     ):
                    #         individual_stats_dict[player_id]["wonduels"] += wins
                    t_winrate = performance["score"][f"{team_key}"]["t"] / (
                        performance["score"][f"{team_key}"]["t"]
                        + performance["score"][f"{away_key}"]["ct"]
                    )
                    individual_stats_dict[player_id]["twinrate"].append(t_winrate)
                    ct_winrate = performance["score"][f"{team_key}"]["ct"] / (
                        performance["score"][f"{team_key}"]["ct"]
                        + performance["score"][f"{away_key}"]["t"]
                    )
                    individual_stats_dict[player_id]["ctwinrate"].append(ct_winrate)
                    ot_winrate = performance["score"][f"{team_key}"]["ot"] + 1 / (
                        performance["score"][f"{team_key}"]["ot"]
                        + performance["score"][f"{away_key}"]["ot"]
                        + 1
                    )
                    individual_stats_dict[player_id]["otwinrate"].append(ot_winrate)
                    for category, condition in condition_dict.items():
                        if condition(performance, player_id):
                            category_stats_dict[player_id][category]["round"][
                                "ct"
                            ].append(performance["score"][team_key]["ct"])
                            category_stats_dict[player_id][category]["round"][
                                "t"
                            ].append(performance["score"][team_key]["t"])
                            category_stats_dict[player_id][category]["rating"][
                                "ct"
                            ].append(
                                performance[team_key + "Stats"][player_id]["ctStats"][
                                    "rating"
                                ]
                            )
                            category_stats_dict[player_id][category]["rating"][
                                "t"
                            ].append(
                                performance[team_key + "Stats"][player_id]["tStats"][
                                    "rating"
                                ]
                            )
        except:
            print("Error processing performance from map", performance["hltvId"])
    # get player-wise averages
    for player_id, player_stats in category_stats_dict.items():
        team_suffix = "team_one" if player_id in team_one_ids else "team_two"
        for category, category_stats in player_stats.items():
            for type, type_stats in category_stats.items():
                if (
                    category == matchup_category
                    and team_suffix == "team_two"
                    and type == "round"
                ):
                    continue
                for side, side_stats in type_stats.items():
                    results_key_mean = f"{type}_avg_{side}_{team_suffix}_{category}"
                    if not results_key_mean in results_dict:
                        results_dict[results_key_mean] = []
                    results_dict[results_key_mean].append(np.mean(side_stats))

                    results_key_stdev = f"{type}_stdev_{side}_{team_suffix}_{category}"
                    if not results_key_stdev in results_dict:
                        results_dict[results_key_stdev] = []
                    results_dict[results_key_stdev].append(
                        np.std(side_stats)
                        if len(side_stats) > 2
                        else default_stdevs[type]
                    )

            results_key_mapsplayed = f"mapsplayed_avg_{team_suffix}_{category}"
            if not results_key_mapsplayed in results_dict:
                results_dict[results_key_mapsplayed] = []
            # TODO: test this
            results_dict[results_key_mapsplayed].append(
                len(list(type_stats.values())[0])
            )
    avg_kasts = {suffix: {"t": [], "ct": []} for suffix in team_suffixes}
    avg_fkdiffs = {suffix: {"t": [], "ct": []} for suffix in team_suffixes}
    avg_ratings = {suffix: {"t": [], "ct": []} for suffix in team_suffixes}
    std_ratings = {suffix: {"t": [], "ct": []} for suffix in team_suffixes}
    # total_wonduels = {suffix: 0 for suffix in team_suffixes}
    # avg_awpkills = {suffix: [] for suffix in team_suffixes}
    # avg_firstkills = {suffix: [] for suffix in team_suffixes}
    avg_twinrate = {suffix: [] for suffix in team_suffixes}
    avg_ctwinrate = {suffix: [] for suffix in team_suffixes}
    avg_otwinrate = {suffix: [] for suffix in team_suffixes}

    for player_id, player_stats in individual_stats_dict.items():
        team_key = "team_one" if player_id in team_one_ids else "team_two"
        # total_wonduels[team_key] += player_stats["wonduels"]
        # avg_awpkills[team_key].append(np.mean(player_stats["awp"]))
        # avg_firstkills[team_key].append(np.mean(player_stats["firstKill"]))
        avg_twinrate[team_key].append(np.mean(player_stats["twinrate"]))
        avg_ctwinrate[team_key].append(np.mean(player_stats["ctwinrate"]))
        avg_otwinrate[team_key].append(np.mean(player_stats["otwinrate"]))
        for side in game_sides:
            avg_kasts[team_key][side].append(np.mean(player_stats["kast"][side]))
            avg_fkdiffs[team_key][side].append(np.mean(player_stats["fkDiff"][side]))
            avg_ratings[team_key][side].append(np.mean(player_stats["rating"][side]))
            std_ratings[team_key][side].append(np.std(player_stats["rating"][side]))

    # essentially get team wise averages
    results_dict = {key: np.mean(values) for key, values in results_dict.items()}

    for suffix in team_suffixes:
        # results_dict[f"total_wonduels_{suffix}"] = np.sum(total_wonduels[suffix])
        # results_dict[f"total_avg_awpkills_{suffix}"] = np.sum(avg_awpkills[suffix])
        # results_dict[f"total_avg_firstkills_{suffix}"] = np.sum(avg_firstkills[suffix])
        results_dict[f"total_avg_twinrate_{suffix}"] = np.sum(avg_twinrate[suffix])
        results_dict[f"total_avg_ctwinrate_{suffix}"] = np.sum(avg_ctwinrate[suffix])
        results_dict[f"total_avg_otwinrate_{suffix}"] = np.sum(avg_otwinrate[suffix])

        if not f"timetogether_{suffix}" in results_dict:
            results_dict[f"timetogether_{suffix}"] = 0
        if not f"lastwin_{suffix}" in results_dict:
            results_dict[f"lastwin_{suffix}"] = default_last
        if not f"lastloss_{suffix}" in results_dict:
            results_dict[f"lastloss_{suffix}"] = default_last
        for side in game_sides:
            results_dict[f"team_avg_ratingvariance_{side}_{suffix}"] = np.std(
                avg_ratings[suffix][side]
                if len(avg_ratings[suffix][side]) > 2
                else default_rating_variance
            )
            results_dict[f"individual_avg_rating_{side}_{suffix}"] = np.mean(
                avg_ratings[suffix][side]
            )
            results_dict[f"individual_avg_ratingvariance_{side}_{suffix}"] = np.mean(
                std_ratings[suffix][side]
            )
            results_dict[f"total_avg_kast_{side}_{suffix}"] = np.sum(
                avg_kasts[suffix][side]
            )
            results_dict[f"total_avg_fkdiff_{side}_{suffix}"] = np.sum(
                avg_fkdiffs[suffix][side]
            )

    return results_dict


def map_condition(map_name):
    return lambda performance, pid: performance["mapType"] == map_name


def online_condition(online):
    return lambda performance, pid: performance["match"][0]["online"] == online


def event_condition(event_id):
    return lambda performance, pid: performance["match"][0]["eventId"] == event_id


ranking_threshold = 4


def intersection_length(lst1, lst2):
    return len(list(set(lst1) & set(lst2)))


def correct_ranking(home_ranking, away_ranking, relative_ranking_int):
    if relative_ranking_int == 0:
        if np.abs(home_ranking - away_ranking) < ranking_threshold:
            return True
    elif relative_ranking_int == 1:
        if home_ranking - away_ranking > ranking_threshold:
            return True
    elif relative_ranking_int == -1:
        if home_ranking - away_ranking < -1 * ranking_threshold:
            return True
    return False


def rank_condition(team_one_ids, team_one_ranking, team_two_ranking):
    # 1 if team1 higher than team2, 0 if theyre similar, -1 if team2 higher than team1
    relative_ranking = 0
    if team_one_ranking - team_two_ranking > ranking_threshold:
        relative_ranking = 1
    elif team_one_ranking - team_two_ranking < -1 * ranking_threshold:
        relative_ranking = -1

    # returns true if a given performance can be used in either teams history against their opposing team's rank
    def valid_ranking_performance(performance, pid):
        home_team_key = None
        away_team_key = None
        if pid in performance["teamOneStats"].keys():
            home_team_key = "teamOne"
            away_team_key = "teamTwo"
        elif pid in performance["teamTwoStats"].keys():
            home_team_key = "teamTwo"
            away_team_key = "teamOne"
        else:
            return False
        return correct_ranking(
            performance[f"{home_team_key}Ranking"] or max_ranking,
            performance[f"{away_team_key}Ranking"] or max_ranking,
            relative_ranking if pid in team_one_ids else -1 * relative_ranking,
        )

    return valid_ranking_performance


def matchup_condition(team_one_ids, team_two_ids):
    return lambda performance, pid: (
        intersection_length(team_one_ids, performance["teamOneStats"].keys()) >= 3
        and intersection_length(team_two_ids, performance["teamTwoStats"].keys()) >= 3
    ) or (
        intersection_length(team_one_ids, performance["teamTwoStats"].keys()) >= 3
        and intersection_length(team_two_ids, performance["teamOneStats"].keys()) >= 3
    )


def generate_data_point(curr_map, played=True, map_info=None):
    try:
        w = {}
        related_match = curr_map["match"][0] if played else None
        related_event = curr_map["event"][0]
        winner = np.random.randint(2) if played else 1
        raw_date = related_match["date"] if played else curr_map["date"]
        map_name = curr_map["mapType"] if played else map_info["map_name"]
        # TODO: deceiving, since sometimes match id if unplaeyd
        w["map_id"] = curr_map["hltvId"]
        w["map_date"] = quantize_time(raw_date)
        team_one_ids = (
            [
                str(pid)
                for pid in curr_map[
                    "teamOneStats" if winner == 1 else "teamTwoStats"
                ].keys()
            ]
            if played
            else [str(pid) for pid in curr_map["players"]["firstTeam"]]
        )
        team_two_ids = (
            [
                str(pid)
                for pid in curr_map[
                    "teamTwoStats" if winner == 1 else "teamOneStats"
                ].keys()
            ]
            if played
            else [str(pid) for pid in curr_map["players"]["secondTeam"]]
        )
        if len(team_one_ids) != 5 or len(team_two_ids) != 5:
            # print(w["map_id"], "Non-five team sizes")
            return None
        online = related_match["online"] if played else curr_map["online"]
        w["online_bool"] = online
        w["event_teamnum"] = related_event["teamNum"]
        w["bestof"] = related_match["numMaps"] if played else curr_map["numMaps"]
        # w["match_category"] = related_match["matchTypeCategory"]
        event_team_rankings = np.array(
            list(
                map(
                    # normalizes rankings by subtracting them by max observed ranking and turning to 0 if it's null
                    lambda ranking: max_ranking - ranking if ranking != None else 0,
                    related_event["teamRankings"],
                )
            )
        )
        # mean and stdev of team rankings at event
        event_team_rankings_analyzed = {
            "event_avg_rankings": np.mean(event_team_rankings),
            "event_stdev_rankings": np.std(event_team_rankings),
        }
        w |= event_team_rankings_analyzed

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
        w["ranking_team_one"] = ranking_one if winner == 1 else ranking_two
        w["ranking_team_two"] = ranking_two if winner == 1 else ranking_one

        team_one_ages = [default_birth_year - min_birth_year]
        team_two_ages = [default_birth_year - min_birth_year]

        picked_by = curr_map.get("pickedBy", "") if played else map_info["picked_by"]

        team_one_key = "teamOne" if winner == 1 else "teamTwo"
        team_two_key = "teamTwo" if winner == 1 else "teamOne"

        w["map_pick_team_one"] = picked_by == team_one_key
        w["map_pick_team_two"] = picked_by == team_two_key

        w["map_num"] = curr_map.get("mapNum", 0) if played else map_info["map_num"]

        for player in (
            curr_map["players_info"]
            if played
            else curr_map["players_info_first"] + curr_map["players_info_second"]
        ):
            if player["birthYear"] != None:
                adjusted_birth_year = player["birthYear"] - min_birth_year
                if str(player["hltvId"]) in team_one_ids:
                    team_one_ages.append(adjusted_birth_year)
                elif str(player["hltvId"]) in team_two_ids:
                    team_two_ages.append(adjusted_birth_year)

        w["age_avg_team_one"] = np.mean(team_one_ages)
        w["age_avg_team_two"] = np.mean(team_two_ages)

        w |= get_map_vector(map_name)

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
                                {"date": {"$gte": raw_date - max_threshold}},
                                {
                                    "players": {
                                        "$in": [
                                            int(pid)
                                            for pid in team_one_ids + team_two_ids
                                        ]
                                    }
                                },
                            ]
                        }
                    },
                    {"$sort": {"date": -1}},
                ]
            )
        )

        # print(f"ID: {w['map_id']}, performance #: {len(performances)}")

        condition_dict = {
            matchup_category: matchup_condition(team_one_ids, team_two_ids),
            "map": map_condition(map_name),
            "online": online_condition(online),
            "event": event_condition(related_event["hltvId"]),
            "rank": rank_condition(
                team_one_ids, w["ranking_team_one"], w["ranking_team_two"]
            ),
        }

        results_data = generate_round_rating_stats(
            team_one_ids, team_two_ids, performances, condition_dict, raw_date
        )
        w |= results_data

        if played:
            team_one_score = (
                curr_map["score"][team_one_key]["ct"]
                + curr_map["score"][team_one_key]["t"]
                + curr_map["score"][team_one_key]["ot"]
            )
            team_two_score = (
                curr_map["score"][team_two_key]["ct"]
                + curr_map["score"][team_two_key]["t"]
                + curr_map["score"][team_two_key]["ot"]
            )
            if team_one_score == team_two_score:
                winner = 0.5
            w["winner"] = winner
            for side in ["ct", "t", "ot"]:
                w[f"map_score_{side}_team_one"] = curr_map["score"][team_one_key][side]
                w[f"map_score_{side}_team_two"] = curr_map["score"][team_two_key][side]

        return w
    except Exception as e:
        print("Unable to process map id", curr_map["hltvId"])
        print(traceback.format_exc())
        return None


def process_maps(maps_to_process, frame_lock, feature_data, thread_idx):
    # print(f"New map processor started: [{thread_idx}]")
    for map_idx in tqdm(
        range(len(maps_to_process)), desc=f"Map Processor [{thread_idx}]", ncols=150
    ):
        curr_map = maps_to_process[map_idx]
        # print(f"[{thread_idx}] Processing map ID:", curr_map["hltvId"])
        w = generate_data_point(curr_map)
        if w == None or len(w.keys()) < feature_data.frame.shape[1]:
            if w == None:
                print("None datapoint")
            else:
                print(
                    "Partial datapoint for map id", w["map_id"], "with length", len(w)
                )
            continue
        with frame_lock:
            feature_data.frame.loc[len(feature_data.frame.index)] = w
    print(f"[{thread_idx}] Done processing maps")

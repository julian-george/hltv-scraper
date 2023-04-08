import pymongo
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["scraped-hltv"]
maps = db["maps"]
matches = db["matches"]
events = db["events"]
players = db["players"]

feature_matrix = np.empty([473, 0])

all_maps = maps.find({})

month_delta = timedelta(1) * 30

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
duel_map_threshold = 6 * month_delta

# max observed team ranking. keep an eye on match rankings to see if any ever approach this
#  as of 4/7/23, max observed ranking is 404
max_ranking = 500


def get_duel_sum(player_id_1, player_id_2, date):
    duel_sum = 0
    duel_performances_one = maps.find(
        {
            "$and": [
                {"date": {"$lt": date, "$gte": date - duel_map_threshold}},
                {f"teamOneStats.{player_id_1}": {"$ne": None}},
                {
                    f"teamOneStats.{player_id_1}.duelMap.all.{player_id_2}": {
                        "$ne": None
                    }
                },
            ]
        }
    )
    for performance in duel_performances_one:
        duel_sum += performance["teamOneStats"][player_id_1]["duelMap"]["all"][
            player_id_2
        ]
    duel_performances_two = maps.find(
        {
            "$and": [
                {"date": {"$lt": date, "$gte": date - duel_map_threshold}},
                {f"teamTwoStats.{player_id_1}": {"$ne": None}},
                {
                    f"teamTwoStats.{player_id_1}.duelMap.all.{player_id_2}": {
                        "$ne": None
                    }
                },
            ]
        }
    )
    for performance in duel_performances_two:
        duel_sum += performance["teamTwoStats"][player_id_1]["duelMap"]["all"][
            player_id_2
        ]
    return duel_sum


# amount of time before a map that rating avg and stdev will be compiled
map_rating_threshold = duel_map_threshold

short_term_threshold = 2 * month_delta

medium_term_threshold = 6 * month_delta

long_term_threshold = 9 * month_delta


# returns a dictionary containing tuple (avg, stdev) for t and ct sides
def get_map_rating_stats(
    player_id, date, map_name=None, rating_threshold=map_rating_threshold
):
    t_ratings = np.array([])
    ct_ratings = np.array([])
    map_performances_one = maps.find(
        {
            "$and": [
                {"date": {"$lt": date, "$gte": date - rating_threshold}},
                {f"teamOneStats.{player_id}": {"$ne": None}},
                {"mapType": map_name} if map_name else {},
            ]
        }
    )
    for performance in map_performances_one:
        np.append(
            t_ratings, (performance["teamOneStats"][player_id]["tStats"]["rating"])
        )
        np.append(
            ct_ratings, (performance["teamOneStats"][player_id]["ctStats"]["rating"])
        )
    map_performances_two = maps.find(
        {
            "$and": [
                {"date": {"$lt": date, "$gte": date - rating_threshold}},
                {f"teamTwoStats.{player_id}": {"$ne": None}},
                {"mapType": map_name} if map_name else {},
            ]
        }
    )
    for performance in map_performances_two:
        np.append(
            t_ratings, (performance["teamTwoStats"][player_id]["tStats"]["rating"])
        )
        np.append(
            ct_ratings, (performance["teamTwoStats"][player_id]["ctStats"]["rating"])
        )

    t_ratings_analyzed = (
        [np.mean(t_ratings), np.std(t_ratings)] if len(t_ratings) > 0 else [0, 0]
    )

    ct_ratings_analyzed = (
        [np.mean(ct_ratings), np.std(ct_ratings)] if len(ct_ratings) > 0 else [0, 0]
    )

    return t_ratings_analyzed + ct_ratings_analyzed


detailed_threshold = duel_map_threshold


def get_detailed_stats(player_id, date):
    t_stats = []
    ct_stats = []
    performances_one = maps.find(
        {
            "$and": [
                {"date": {"$lt": date, "$gte": date - detailed_threshold}},
                {f"teamOneStats.{player_id}": {"$ne": None}},
            ]
        }
    )
    for performance in performances_one:
        t_stats.append(performance["teamOneStats"][player_id]["tStats"])
        ct_stats.append(performance["teamOneStats"][player_id]["ctStats"])

    performances_two = maps.find(
        {
            "$and": [
                {"date": {"$lt": date, "$gte": date - detailed_threshold}},
                {f"teamTwoStats.{player_id}": {"$ne": None}},
            ]
        }
    )
    for performance in performances_two:
        t_stats.append(performance["teamTwoStats"][player_id]["tStats"])
        ct_stats.append(performance["teamTwoStats"][player_id]["ctStats"])
    t_stats = pd.DataFrame(t_stats).to_dict(orient="list")
    ct_stats = pd.DataFrame(ct_stats).to_dict(orient="list")
    t_stats_analyzed = (
        [
            np.mean(t_stats["kills"]),
            np.std(t_stats["kills"]),
            np.mean(t_stats["hsKills"]),
            np.std(t_stats["hsKills"]),
            np.mean(t_stats["assists"]),
            np.std(t_stats["assists"]),
            # add flash assists??
            np.mean(t_stats["deaths"]),
            np.std(t_stats["deaths"]),
            np.mean(t_stats["kast"]),
            np.std(t_stats["kast"]),
            np.mean(t_stats["adr"]),
            np.std(t_stats["adr"]),
            np.mean(t_stats["fkDiff"]),
            np.std(t_stats["fkDiff"]),
        ]
        if len(t_stats) == 10
        else list(np.zeros(14))
    )

    ct_stats_analyzed = (
        [
            np.mean(ct_stats["kills"]),
            np.std(ct_stats["kills"]),
            np.mean(ct_stats["hsKills"]),
            np.std(ct_stats["hsKills"]),
            np.mean(ct_stats["assists"]),
            np.std(ct_stats["assists"]),
            np.mean(ct_stats["deaths"]),
            np.std(ct_stats["deaths"]),
            np.mean(ct_stats["kast"]),
            np.std(ct_stats["kast"]),
            np.mean(ct_stats["adr"]),
            np.std(ct_stats["adr"]),
            np.mean(ct_stats["fkDiff"]),
            np.std(ct_stats["fkDiff"]),
        ]
        if len(ct_stats) == 10
        else list(np.zeros(14))
    )

    return t_stats_analyzed + ct_stats_analyzed


for curr_map in all_maps:
    w = []
    related_match = matches.find_one({"hltvId": curr_map["matchId"]})
    raw_date = related_match["date"]
    # datetime rounded to the minute
    date = np.round(raw_date.timestamp() / 60, 0)
    w.append(date)
    # e.g bo1, bo3, etc (replace with numMaps in future)
    format = related_match["formatCategory"]
    w.append(format)

    related_event = events.find_one({"hltvId": related_match["eventId"]})
    # prizepool of event
    #  possibly too inconsistent to be useful, consider removing
    prizepool = related_event["prizePool"] or 0
    w.append(prizepool)
    # if event is online
    online = int(related_event["online"])
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
    w += team_rankings_analyzed

    # series of binary params (multi-classifier) denoting which map is being played
    map_vector = get_map_vector(curr_map["mapType"])
    w += map_vector

    team_one_ids = curr_map["teamOneStats"].keys()
    team_two_ids = curr_map["teamTwoStats"].keys()
    # skip this map if there were more than 5 players per team playing (ie weird substitution/connectivity stuff).
    #   the number of those maps is low so it cuts out outliers while also keeping param vector the same length
    if len(team_one_ids) != 5 or len(team_two_ids) != 5:
        continue
    # calculating duel maps for all of them
    duels = []
    for one_id in team_one_ids:
        for two_id in team_two_ids:
            duels.append(get_duel_sum(one_id, two_id, raw_date))
    w += duels
    ranking_one = (
        max_ranking - curr_map["teamOneRanking"]
        if curr_map["teamOneRanking"] != None
        else 0
    )
    w.append(ranking_one)
    ranking_two = (
        max_ranking - curr_map["teamTwoRanking"]
        if curr_map["teamTwoRanking"] != None
        else 0
    )
    w.append(ranking_two)

    # getting each players recent ratings on the map
    map_performances = []
    # getting ratings on any map over three time frames
    short_term_ratings = []
    medium_term_ratings = []
    long_term_ratings = []
    # big (280-length) array containing mean and stdev of almost all collected stats
    detailed_stats = []
    for one_id in team_one_ids:
        map_performances += get_map_rating_stats(
            one_id, raw_date, map_name=curr_map["mapType"]
        )
        short_term_ratings += get_map_rating_stats(
            one_id, raw_date, rating_threshold=short_term_threshold
        )
        medium_term_ratings += get_map_rating_stats(
            one_id, raw_date, rating_threshold=medium_term_threshold
        )
        long_term_ratings += get_map_rating_stats(
            one_id, raw_date, rating_threshold=long_term_threshold
        )
        detailed_stats += get_detailed_stats(one_id, raw_date)
    for two_id in team_two_ids:
        map_performances += get_map_rating_stats(
            two_id, raw_date, map_name=curr_map["mapType"]
        )
        short_term_ratings += get_map_rating_stats(
            two_id, raw_date, rating_threshold=short_term_threshold
        )
        medium_term_ratings += get_map_rating_stats(
            two_id, raw_date, rating_threshold=medium_term_threshold
        )
        long_term_ratings += get_map_rating_stats(
            two_id, raw_date, rating_threshold=long_term_threshold
        )
        detailed_stats += get_detailed_stats(two_id, raw_date)

    w += map_performances
    w += short_term_ratings
    w += medium_term_ratings
    w += long_term_ratings
    w += detailed_stats
    feature_matrix = np.append(feature_matrix, np.array([w]).T, axis=1)
    print(feature_matrix.shape)

import pymongo
import os
import jellyfish
from datetime import timedelta

client = pymongo.MongoClient(os.environ["MONGODB_URI"])
db = client["scraped-hltv"]
unplayed_matches = db["unplayedmatches"]

# conditions to be added to aggregation pipeline
aggregate_list = [
    {
        "$lookup": {
            "from": "events",
            "localField": "eventId",
            "foreignField": "hltvId",
            "as": "event",
        },
    },
    {
        "$lookup": {
            "from": "players",
            "localField": "players.firstTeam",
            "foreignField": "hltvId",
            "as": "players_info_first",
        }
    },
    {
        "$lookup": {
            "from": "players",
            "localField": "players.secondTeam",
            "foreignField": "hltvId",
            "as": "players_info_second",
        }
    },
    {"$sort": {"date": -1}},
]

unplayed_threshold = timedelta(days=0, hours=7, minutes=0)
threshold_similarity = 0.8


def get_unplayed_match_by_team_names(team_one_name, team_two_name, date=None):
    team_one_name = team_one_name.lower()
    team_two_name = team_two_name.lower()
    draft_title_1 = f"{team_one_name} vs. {team_two_name}"
    draft_title_2 = f"{team_two_name} vs. {team_one_name}"
    all_unplayed = list(
        unplayed_matches.aggregate(
            [
                {"$match": {"played": {"$ne": True}}},
            ]
            + aggregate_list
        )
    )
    best_match = None
    best_similarity = 0
    for unplayed in all_unplayed:
        match_title = unplayed["title"]
        # TODO: weigh shared substrings heavily
        curr_similarity = max(
            jellyfish.jaro_similarity(match_title, draft_title_1),
            jellyfish.jaro_similarity(match_title, draft_title_2),
        )
        # print(match_title, draft_title_1, draft_title_2, curr_similarity)
        if curr_similarity > best_similarity and curr_similarity > threshold_similarity:
            if date == None or abs(date - unplayed["date"]) < unplayed_threshold:
                best_match = unplayed
                best_similarity = curr_similarity
    if best_match == None:
        return None, True
    team_names = best_match["title"].split(" vs. ")
    same_order = jellyfish.jaro_similarity(
        team_one_name, team_names[0]
    ) > jellyfish.jaro_similarity(team_one_name, team_names[1])
    print(draft_title_1, best_match["title"])
    print("bestsimilarity", best_similarity, "sameorder", same_order)
    return best_match, same_order


def get_cached_predictions(matchId, same_order):
    match = unplayed_matches.find_one({"hltvId": matchId})
    if not match or "predictions" not in match or match["predictions"] == None:
        return None
    map_predictions = match["predictions"]
    for map_name, predictions in map_predictions.items():
        if not same_order:
            map_predictions[map_name] = predictions.reverse()
    return map_predictions


def confirm_bet(matchId, betted_markets):
    # print("confirming", betted_markets)
    unplayed_match = unplayed_matches.find_one({"hltvId": matchId})
    betted_markets = {**unplayed_match["betted"], **betted_markets}
    unplayed_matches.update_one(
        {"hltvId": matchId}, {"$set": {"betted": betted_markets}}
    )
    return betted_markets


def set_maps(matchId, maps):
    unplayed_matches.update_one({"hltvId": matchId}, {"$set": {"mapInfos": maps}})


def cache_predictions(matchId, prediction_dict):
    for map_name, predictions in prediction_dict.items():
        predictions = [float(prediction) for prediction in predictions]
        prediction_dict[map_name] = predictions
    unplayed_matches.update_one(
        {"hltvId": matchId}, {"$set": {"predictions": prediction_dict}}
    )


def get_all_unplayed_matches():
    return unplayed_matches.aggregate(
        [
            {"$match": {"played": {"$ne": True}}},
        ]
        + aggregate_list
    )


def get_unplayed_match_by_id(id):
    match_cursor = unplayed_matches.aggregate(
        [{"$match": {"hltvId": int(id)}}] + aggregate_list
    )
    if not match_cursor._has_next():
        return None
    return match_cursor.next()


url_prefix = "https://www.hltv.org"


def get_match_url_by_id(match_id):
    return url_prefix + unplayed_matches.find_one({"hltvId": match_id})["matchUrl"]


def get_match_title_by_id(match_id):
    return unplayed_matches.find_one({"hltvId": match_id})["title"]

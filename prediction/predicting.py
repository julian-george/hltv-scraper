import pymongo
import re
import sys
import pandas as pd
import tensorflow as tf
import os
from processing_helper import generate_data_point
from learning_helper import process_frame


client = pymongo.MongoClient(os.environ["MONGODB_URI"])
db = client["scraped-hltv"]
unplayed_matches = db["unplayedmatches"]
matches = db["matches"]
maps = db["maps"]

model_name = "prediction_model"
model = tf.keras.models.load_model(model_name)

# conditions to be added to aggregation pipeline
aggregate_list = [
    # {"$match": {"betted": {"$size": 0}}},
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

# Update this as Active Duty maps change
map_types = [
    "Ancient",
    "Anubis",
    "Inferno",
    "Mirage",
    "Nuke",
    "Overpass",
    "Vertigo",
]


def trim_team_name(team_name):
    team_name = team_name.replace("GG", "").lower()
    team_name = (
        team_name.replace("gaming", "")
        .replace("team", "")
        .replace("esports", "")
        .replace("esport", "")
        .replace("e-sports", "")
    )
    if team_name[-1] == ".":
        team_name = team_name[:-1]
    split_team_name = team_name.split(" ")
    if split_team_name[0] == "the":
        split_team_name.pop(0)
    team_name = " ".join(split_team_name)
    team_name = re.sub(" +", " ", team_name).strip()
    team_name = team_name
    return team_name


def get_cached_predictions(matchId, same_order):
    match = unplayed_matches.find_one({"hltvId": matchId})
    if not match or "predictions" not in match or match["predictions"] == None:
        return None
    map_predictions = match["predictions"]
    for map_name, predictions in map_predictions.items():
        if not same_order:
            map_predictions[map_name] = predictions.reverse()
    return map_predictions


def cache_predictions(matchId, prediction_dict):
    for map_name, predictions in prediction_dict.items():
        predictions = [float(prediction) for prediction in predictions]
        prediction_dict[map_name] = predictions
    unplayed_matches.update_one(
        {"hltvId": matchId}, {"$set": {"predictions": prediction_dict}}
    )


def generate_prediction(match, same_order=True, ignore_cache=False):
    if not ignore_cache:
        cached_predictions = get_cached_predictions(match["hltvId"], same_order)
        if cached_predictions != None:
            return cached_predictions
    print("Generating new predictions...")
    map_predictions = {}
    for map_type in map_types:
        w = generate_data_point(match, played=False, map_name=map_type)
        processed_w = process_frame(pd.DataFrame([w]))[0]
        # with open("t.txt", "w") as f:
        #     f.write("\n".join(sorted(list(processed_w.columns))))
        processed_w.to_csv("test.csv")
        processed_w = processed_w.to_numpy()
        prediction = list(model.predict(processed_w, verbose=False)[0])
        map_predictions[map_type] = prediction
    cache_predictions(match["hltvId"], map_predictions)
    for map_name, predictions in map_predictions.items():
        if not same_order:
            map_predictions[map_name] = predictions.reverse()
    return map_predictions


def predict_match(team_one_name, team_two_name):
    team_one_name = trim_team_name(team_one_name)
    team_two_name = trim_team_name(team_two_name)
    same_order = True
    regex_query = {
        "$match": {
            "$and": [
                {"title": {"$regex": team_one_name}},
                {"title": {"$regex": team_two_name}},
            ]
        }
    }
    match = unplayed_matches.aggregate([regex_query] + aggregate_list)
    if not match._has_next():
        return ({}, None)
    match = match.next()
    print(team_one_name, team_two_name, match["title"])
    if match["title"].index(team_one_name) > match["title"].index(team_two_name):
        same_order = False
    map_predictions = generate_prediction(match, same_order)
    return (map_predictions, match)


def predict_all_matches():
    all_matches = list(unplayed_matches.aggregate(aggregate_list))
    print("Predicting", len(all_matches), "matches...")
    predictions = {}
    for match in all_matches:
        predictions[match["title"]] = generate_prediction(match)
    return predictions


if __name__ == "__main__":
    if len(sys.argv) == 1:
        all_predictions = predict_all_matches()
        for title, pred in all_predictions.items():
            print(title)
            for map_name, odds in pred.items():
                print("\t", map_name, odds)
    elif len(sys.argv) == 3:
        prediction = predict_match(sys.argv[1], sys.argv[2])
        if prediction[1] == None:
            print("No such match found")
        else:
            print(sys.argv[1], "vs.", sys.argv[2])
            for map_name, odds in prediction[0].items():
                print("\t", map_name, odds)


def set_maps(matchId, maps):
    unplayed_matches.update_one({"hltvId": matchId}, {"$set": {"mapNames": maps}})


def confirm_bet(matchId, betted_markets):
    unplayed_match = unplayed_matches.find_one({"hltvId": matchId})
    betted_markets = {**unplayed_match["betted"], **betted_markets}
    unplayed_matches.update_one(
        {"hltvId": matchId}, {"$set": {"betted": betted_markets}}
    )


def map_ids_to_examine():
    ids = []
    all_unplayed = list(unplayed_matches.find({}))
    for unplayed in all_unplayed:
        hltv_id = unplayed["hltvId"]
        played = matches.find_one({"hltvId": hltv_id})
        if played:
            related_maps = list(maps.find({"matchId": played["hltvId"]}))
            for r_map in related_maps:
                ids.append(r_map["hltvId"])
    return ids

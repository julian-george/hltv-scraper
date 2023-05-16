import pymongo
import re
import pandas as pd
import tensorflow as tf
import os
from processing_helper import generate_data_point
from learning_helper import process_frame


client = pymongo.MongoClient(os.environ["MONGODB_URI"])
db = client["scraped-hltv"]
unplayed_matches = db["unplayedmatches"]

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
    team_name = team_name.replace("Gaming", "").replace("GG", "").replace("Team", "")
    team_name = re.sub(" +", " ", team_name).strip()
    return team_name


def generate_prediction(match, same_order=True):
    map_predictions = {}
    for map_type in map_types:
        w = generate_data_point(match, played=False, map_type=map_type)
        processed_w = process_frame(pd.DataFrame([w]))[0]
        processed_w = processed_w.to_numpy()
        prediction = list(model.predict(processed_w, verbose=False)[0])
        map_predictions[map_type] = prediction if same_order else prediction.reverse()
    return map_predictions


def predict_match(team_one_name, team_two_name):
    team_one_name = trim_team_name(team_one_name)
    team_two_name = trim_team_name(team_two_name)
    same_order = True
    match = unplayed_matches.aggregate(
        aggregate_list + [{"$match": {"title": f"{team_one_name} vs. {team_two_name}"}}]
    )
    if not match._has_next():
        same_order = False
        match = unplayed_matches.aggregate(
            aggregate_list
            + [{"$match": {"title": f"{team_two_name} vs. {team_one_name}"}}]
        )
    if not match._has_next():
        return ({}, None)
    match = match.next()
    map_predictions = generate_prediction(match, same_order)
    return (map_predictions, match)


def predict_all_matches():
    all_matches = list(unplayed_matches.aggregate(aggregate_list))
    print("Predicting", len(all_matches), "matches...")
    predictions = {}
    for match in all_matches:
        predictions[match["title"]] = generate_prediction(match)
    return predictions


all_predictions = predict_all_matches()
for title, pred in all_predictions.items():
    print(title)
    for map_name, odds in pred.items():
        print("\t", map_name, odds)


def confirm_bet(matchId, map_num):
    unplayed_matches.update_one({"hltvId": matchId}, {"$push": {"betted": map_num}})

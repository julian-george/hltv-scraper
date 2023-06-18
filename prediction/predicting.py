import pymongo
import sys
import pandas as pd
import tensorflow as tf
import os
import jellyfish
from datetime import timedelta, datetime
from processing_helper import generate_data_point
from learning_helper import process_frame


client = pymongo.MongoClient(os.environ["MONGODB_URI"])
db = client["scraped-hltv"]
unplayed_matches = db["unplayedmatches"]
matches = db["matches"]
maps = db["maps"]

model_name = "prediction_model"


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


default_map_infos = [
    {"map_name": map_name, "picked_by": None, "map_num": 0} for map_name in map_types
]


def generate_prediction(match, map_infos=None, same_order=True, ignore_cache=False):
    if map_infos == None:
        print("No map infos provided, using default.")
        map_infos = default_map_infos
    if not ignore_cache:
        cached_predictions = get_cached_predictions(match["hltvId"], same_order)
        if (
            cached_predictions != None
            and not None in cached_predictions.values()
            and cached_predictions != {}
        ):
            print("Returning cached predictions...")
            return cached_predictions
    print("Generating new predictions...")
    model = tf.keras.models.load_model(model_name)
    map_predictions = {}
    for i, map_info in enumerate(map_infos):
        w = generate_data_point(match, played=False, map_info=map_info)
        processed_w = process_frame(pd.DataFrame([w]))[0]
        # with open("t.txt", "w") as f:
        #     f.write("\n".join(sorted(list(processed_w.columns))))
        processed_w.to_csv(f"w_{i}_unplayed.csv")
        processed_w = processed_w.to_numpy()
        prediction = list(model.predict(processed_w, verbose=False)[0])
        map_predictions[map_info["map_name"]] = prediction
    cache_predictions(match["hltvId"], map_predictions)
    for map_name, predictions in map_predictions.items():
        if not same_order:
            map_predictions[map_name].reverse()
        map_predictions[map_name] = [round(prediction, 3) for prediction in predictions]
    return map_predictions


def get_match_by_id(id):
    match_cursor = unplayed_matches.aggregate(
        [{"$match": {"hltvId": int(id)}}] + aggregate_list
    )
    if not match_cursor._has_next():
        return None
    return match_cursor.next()


unplayed_threshold = timedelta(days=0, hours=7, minutes=0)
threshold_similarity = 0.7


def get_unplayed_match_by_team_names(team_one_name, team_two_name, date=None):
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
        curr_similarity = max(
            jellyfish.jaro_similarity(unplayed["title"], draft_title_1),
            jellyfish.jaro_similarity(unplayed["title"], draft_title_2),
        )
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
    print("bestsimilarity", best_similarity)
    return best_match, same_order


def predict_match(match, map_infos, same_order=True):
    map_predictions = generate_prediction(match, map_infos, same_order)
    return map_predictions


def maps_to_examine():
    map_list = []
    all_unplayed = list(unplayed_matches.find({}))
    for unplayed in all_unplayed:
        hltv_id = unplayed["hltvId"]
        played = matches.find_one({"hltvId": hltv_id})
        if played:
            related_maps = list(maps.find({"matchId": played["hltvId"]}))
            for r_map in related_maps:
                map_list.append(r_map)
    return map_list


def map_ids_to_examine():
    maps = maps_to_examine()
    return [map_dict["hltvId"] for map_dict in maps]


def match_ids_to_examine():
    maps = maps_to_examine()
    return [map_dict["matchId"] for map_dict in maps]


def predict_all_matches():
    all_matches = list(
        unplayed_matches.aggregate(
            [
                {"$match": {"played": {"$ne": True}}},
            ]
            + aggregate_list
        )
    )
    played_match_ids = match_ids_to_examine()
    all_unplayed = [
        match for match in all_matches if not match["hltvId"] in played_match_ids
    ]
    print("Predicting", len(all_unplayed), "matches...")
    predictions = {}
    for match in all_unplayed:
        predictions[match["title"]] = generate_prediction(match)
    return predictions


if __name__ == "__main__":
    if len(sys.argv) == 1:
        all_predictions = predict_all_matches()

        for title, pred in all_predictions.items():
            print(title)
            for map_name, odds in pred.items():
                print("\t", map_name, odds)
    else:
        team_names = []
        same_order = True
        if len(sys.argv) == 2:
            match = get_match_by_id(sys.argv[1])
            team_names = match["title"].split(" vs. ")

        elif len(sys.argv) == 3:
            match, same_order = get_unplayed_match_by_team_names(
                sys.argv[1], sys.argv[2]
            )
            team_names = [sys.argv[1], sys.argv[2]]
        prediction = predict_match(
            match, match["mapInfos"] or default_map_infos, same_order
        )
        if prediction == None:
            print("No such match found")
        else:
            print(team_names[0], "vs.", team_names[1])
            for map_name, odds in prediction.items():
                print("\t", map_name, odds)


def set_maps(matchId, maps):
    unplayed_matches.update_one({"hltvId": matchId}, {"$set": {"mapInfos": maps}})


def confirm_bet(matchId, betted_markets):
    unplayed_match = unplayed_matches.find_one({"hltvId": matchId})
    betted_markets = {**unplayed_match["betted"], **betted_markets}
    unplayed_matches.update_one(
        {"hltvId": matchId}, {"$set": {"betted": betted_markets}}
    )
    return betted_markets

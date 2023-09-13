import sys
import pandas as pd
import tensorflow as tf
from datetime import datetime

from processing_helper import generate_data_point
from learning_helper import process_frame
from services.unplayedmatch_service import (
    get_all_unplayed_matches,
    get_cached_predictions,
    get_unplayed_match_by_id,
    get_unplayed_match_by_team_names,
    cache_predictions,
)
from services.map_service import maps_to_examine


model_name = "prediction_model"
csv_folder = "learning_data/"


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


default_map_infos = [
    {"map_name": map_name, "picked_by": None, "map_num": 0} for map_name in map_types
]


def predict_match(match, map_infos=None, same_order=True, ignore_cache=False):
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
        # print(processed_w)
        # with open("t.txt", "w") as f:
        #     f.write("\n".join(sorted(list(processed_w.columns))))
        processed_w.to_csv(csv_folder + f"w_{i}_unplayed.csv")
        processed_w = processed_w.to_numpy()
        prediction = list(model.predict(processed_w, verbose=False)[0])
        map_predictions[map_info["map_name"]] = prediction
    cache_predictions(match["hltvId"], map_predictions)
    for map_name, predictions in map_predictions.items():
        if not same_order:
            map_predictions[map_name].reverse()
        map_predictions[map_name] = [round(prediction, 5) for prediction in predictions]
    return map_predictions


def map_ids_to_examine():
    maps = maps_to_examine()
    return [map_dict["hltvId"] for map_dict in maps]


def match_ids_to_examine():
    maps = maps_to_examine()
    return [map_dict["matchId"] for map_dict in maps]


def predict_all_matches():
    all_matches = get_all_unplayed_matches()
    played_match_ids = match_ids_to_examine()
    all_unplayed = [
        match for match in all_matches if not match["hltvId"] in played_match_ids
    ]
    print("Predicting", len(all_unplayed), "matches...")
    predictions = {}
    for match in all_unplayed:
        predictions[match["title"]] = predict_match(match)
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
            match = get_unplayed_match_by_id(sys.argv[1])
            team_names = match["title"].split(" vs. ")

        elif len(sys.argv) == 3:
            match, same_order = get_unplayed_match_by_team_names(
                sys.argv[1], sys.argv[2], date=datetime.now()
            )
            team_names = [sys.argv[1], sys.argv[2]]
        prediction = predict_match(
            match, match["mapInfos"] or default_map_infos, same_order, ignore_cache=True
        )
        if prediction == None:
            print("No such match found")
        else:
            print(team_names[0], "vs.", team_names[1])
            for map_name, odds in prediction.items():
                print("\t", map_name, odds)

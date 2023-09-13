import pymongo
import json
import atexit
import threading
import numpy as np
import pandas as pd
import time
import os
import threading
import tensorflow as tf
from datetime import datetime
from types import SimpleNamespace
from processing_helper import process_maps, generate_data_point
from predicting import process_frame

client = pymongo.MongoClient(os.environ["MONGODB_URI"])
db = client["scraped-hltv"]
maps = db["maps"]

csv_folder = "learning_data/"

lookup_aggregation = [
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
        "$lookup": {
            "from": "players",
            "localField": "players",
            "foreignField": "hltvId",
            "as": "players_info",
        }
    },
]


def predict_played_match(hltv_id):
    played_maps = list(
        maps.aggregate([{"$match": {"matchId": int(hltv_id)}}] + lookup_aggregation)
    )
    return {m["mapType"]: predict_map(m, i) for i, m in enumerate(played_maps)}


model_name = "prediction_model"


def predict_map(map, i):
    model = tf.keras.models.load_model(model_name)
    w = generate_data_point(map)
    same_order = w["winner"] == 1
    winner = w["winner"]
    del w["winner"]
    processed_w = process_frame(pd.DataFrame([w]))[0]
    processed_w.to_csv(csv_folder + f"w_{i}_played.csv")
    prediction = list(model.predict(processed_w.to_numpy())[0].round(5))
    # if not same_order:
    #     prediction.reverse()
    return prediction, winner


if __name__ == "__main__":
    frame_file_path = csv_folder + "frame.csv"
    map_history_file_path = csv_folder + "processed-maps.json"

    # we use this so that the matrix is mutated, not replaced, within threads
    feature_data = SimpleNamespace()

    column_names = []

    column_names.append("winner")
    column_names.append("map_date")
    column_names.append("online_bool")
    column_names.append("event_teamnum")
    column_names.append("event_avg_rankings")
    column_names.append("event_stdev_rankings")
    column_names.append("bestof")
    column_names.append("map_id")
    column_names.append("map_num")

    # extremely flawed metric but
    # column_names.append("match_category")

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

    for map in map_list:
        column_names.append(f"map_{map.lower()}_bool")

    team_suffixes = ["team_one", "team_two"]
    sides = ["ct", "t"]
    stat_types = ["avg", "stdev"]

    round_stats_columns = []
    rating_stats_columns = []
    for suffix in team_suffixes:
        for side in sides:
            column_names.append(f"team_avg_ratingvariance_{side}_{suffix}")
            # probably redundant
            column_names.append(f"individual_avg_rating_{side}_{suffix}")
            column_names.append(f"individual_avg_ratingvariance_{side}_{suffix}")
            column_names.append(f"total_avg_kast_{side}_{suffix}")
            column_names.append(f"total_avg_fkdiff_{side}_{suffix}")

            for type in stat_types:
                round_stats_columns.append(f"round_{type}_{side}_{suffix}")
                rating_stats_columns.append(f"rating_{type}_{side}_{suffix}")
            column_names.append(f"map_score_{side}_{suffix}")
        # shared between round stats and rating stats
        rating_stats_columns.append(f"mapsplayed_avg_{suffix}")
        column_names.append(f"ranking_{suffix}")
        column_names.append(f"age_avg_{suffix}")
        # column_names.append(f"total_wonduels_{suffix}")
        column_names.append(f"timetogether_{suffix}")
        column_names.append(f"lastwin_{suffix}")
        column_names.append(f"lastloss_{suffix}")

        # column_names.append(f"total_avg_awpkills_{suffix}")

        column_names.append(f"total_avg_twinrate_{suffix}")
        column_names.append(f"total_avg_ctwinrate_{suffix}")
        column_names.append(f"total_avg_otwinrate_{suffix}")

        column_names.append(f"map_pick_{suffix}")

        column_names.append(f"map_score_ot_{suffix}")

    matchup_category = "matchup"

    stat_categories = ["rank", "map", "online", "event", matchup_category]

    for category in stat_categories:
        round_category_columns = [f"{col}_{category}" for col in round_stats_columns]
        rating_category_columns = [f"{col}_{category}" for col in rating_stats_columns]
        if category == matchup_category:
            round_category_columns = [
                col for col in round_category_columns if not team_suffixes[1] in col
            ]
        column_names += round_category_columns
        column_names += rating_category_columns
        # feature_data.matrix = np.empty([0, 630])
        feature_data.frame = pd.DataFrame(columns=column_names)
        feature_data.history = set()
        # feature_data.history = None

    try:
        feature_data.frame = pd.read_csv(frame_file_path, index_col=[0])
        feature_data.history = set(feature_data.frame["map_id"])
        print("Feature frame loaded, shape", feature_data.frame.shape)
    except:
        print(f"Unable to load frame from {frame_file_path}.")

    def save_frame():
        print(f"Saving frame to {frame_file_path}, shape", feature_data.frame.shape)
        feature_data.frame.sort_values(by=["map_id"], inplace=True)
        feature_data.frame.to_csv(frame_file_path)

    start_time = datetime.now()
    initial_map_num = len(feature_data.history or [])

    def print_process_rate():
        end_time = datetime.now()
        elapsed_time = end_time - start_time
        elapsed_time = elapsed_time.seconds / 60
        feature_data.history = set(feature_data.frame["map_id"])
        if feature_data.history != None:
            final_map_num = len(feature_data.history)
            maps_processed = final_map_num - initial_map_num
            maps_per_minute = maps_processed / elapsed_time
            print(f"Average of {maps_per_minute} processed per minute.")

    atexit.register(save_frame)
    atexit.register(print_process_rate)

    num_maps = maps.count_documents(
        {"hltvId": {"$not": {"$in": list(feature_data.history or [])}}}
    )

    thread_num = 16

    slice_size = np.ceil(num_maps / thread_num)

    print(f"Processing {num_maps} maps in {thread_num} slices of {slice_size}")

    frame_lock = threading.Lock()
    history_lock = threading.Lock()
    exit_lock = threading.Lock()

    for i in range(thread_num):
        maps_slice = list(
            maps.aggregate(
                [
                    {
                        "$match": {
                            "hltvId": {
                                "$not": {"$in": list(feature_data.history or [])}
                            }
                        }
                    },
                    {"$sort": {"hltvId": -1}},
                    {"$skip": slice_size * i},
                    {"$limit": slice_size},
                ]
                + lookup_aggregation,
                allowDiskUse=True,
            )
        )
        # print([m["hltvId"] for m in maps_slice])
        threading.Thread(
            target=process_maps,
            args=(maps_slice, frame_lock, feature_data, i),
        ).start()
        time.sleep(1)

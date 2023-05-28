import pymongo
import json
import atexit
import threading
import numpy as np
import pandas as pd
import time
import os
import threading
from datetime import datetime
from types import SimpleNamespace
from processing_helper import process_maps

client = pymongo.MongoClient(os.environ["MONGODB_URI"])
db = client["scraped-hltv"]
maps = db["maps"]

frame_file_path = "./frame.csv"
map_history_file_path = "./processed-maps.json"

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
        for type in stat_types:
            round_stats_columns.append(f"round_{type}_{side}_{suffix}")
            rating_stats_columns.append(f"rating_{type}_{side}_{suffix}")
    # shared between round stats and rating stats
    rating_stats_columns.append(f"mapsplayed_avg_{suffix}")
    column_names.append(f"ranking_{suffix}")
    column_names.append(f"age_avg_{suffix}")
    column_names.append(f"total_wonduels_{suffix}")
    column_names.append(f"timetogether_{suffix}")
    column_names.append(f"lastwin_{suffix}")
    column_names.append(f"lastloss_{suffix}")

    column_names.append(f"total_avg_awpkills_{suffix}")
    column_names.append(f"total_avg_firstkills_{suffix}")

    column_names.append(f"total_avg_twinrate_{suffix}")
    column_names.append(f"total_avg_ctwinrate_{suffix}")
    column_names.append(f"total_avg_otwinrate_{suffix}")

    # column_names.append(f"map_pick_{suffix}")


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
feature_data.to_exit = False

try:
    feature_data.frame = pd.read_csv(frame_file_path, index_col=[0])
    print("Feature frame loaded, shape", feature_data.frame.shape)
except:
    print(f"Unable to load frame from {frame_file_path}.")

try:
    map_history_file = open(map_history_file_path, "r")
    feature_data.history = set(json.loads(map_history_file.read()))
    map_history_file.close()
    print("Map history file loaded, length:", len(feature_data.history))
except:
    print(f"Unable to load map history from {map_history_file_path}")


def signal_exit():
    feature_data.to_exit = True


def save_frame():
    print(f"Saving frame to {frame_file_path}, shape", feature_data.frame.shape)
    feature_data.frame.sort_values(by=["map_id"])
    feature_data.frame.to_csv(frame_file_path)


def save_map_history():
    if feature_data.history != None:
        map_history_file = open(map_history_file_path, "w+")
        map_history_file.write(json.dumps(list(feature_data.history)))
        map_history_file.close()


start_time = datetime.now()
initial_map_num = len(feature_data.history or [])


def print_process_rate():
    end_time = datetime.now()
    elapsed_time = end_time - start_time
    elapsed_time = elapsed_time.seconds / 60
    if feature_data.history != None:
        final_map_num = len(feature_data.history)
        maps_processed = final_map_num - initial_map_num
        maps_per_minute = maps_processed / elapsed_time
        print(f"Average of {maps_per_minute} processed per minute.")


atexit.register(signal_exit)
atexit.register(save_map_history)
atexit.register(save_frame)
atexit.register(print_process_rate)

num_maps = maps.count_documents({})

thread_num = 8

slice_size = np.ceil(num_maps / thread_num)

frame_lock = threading.Lock()
history_lock = threading.Lock()
exit_lock = threading.Lock()

for i in range(thread_num):
    maps_slice = list(
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
                    "$lookup": {
                        "from": "players",
                        "localField": "players",
                        "foreignField": "hltvId",
                        "as": "players_info",
                    }
                },
                {"$sort": {"date": -1}},
                {"$skip": slice_size * i},
                {"$limit": slice_size},
            ],
            allowDiskUse=True,
        )
    )

    threading.Thread(
        target=process_maps,
        args=(maps_slice, frame_lock, history_lock, exit_lock, feature_data, i),
    ).start()
    time.sleep(1)

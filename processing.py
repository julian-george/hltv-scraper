import pymongo
import json
import atexit
import threading
import numpy as np
import pandas as pd
import time
import os
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

team_prefixes = ["team_one", "team_two"]
sides = ["ct", "t"]

column_names = [
    "map_date",
    "match_num_maps",
    "event_prize_pool",
    "online",
    "event_team_rankings_mean",
    "event_team_rankings_std",
    "team_one_ranking",
    "team_two_ranking",
]

column_names += [
    "map_ancient_bool",
    "map_anubis_bool",
    "map_cache_bool",
    "map_cobblestone_bool",
    "map_dust2_bool",
    "map_inferno_bool",
    "map_mirage_bool",
    "map_nuke_bool",
    "map_overpass_bool",
    "map_train_bool",
    "map_vertigo_bool",
]

column_names += [f"duel_team_one_{i}_{j}" for j in range(5) for i in range(5)]
column_names += [f"duel_team_two_{i}_{j}" for j in range(5) for i in range(5)]

stat_types = ["overall", "map", "event"]

for pref in team_prefixes:
    for type in stat_types:
        column_names += [
            f"{pref}_win_num_{type}",
            f"{pref}_played_num_{type}",
            f"{pref}_mean_rounds_{type}",
        ]
        if type == "event":
            for side in sides:
                column_names += [
                    f"{pref}_player_{i}_{side}_rating_avg_event" for i in range(5)
                ]

time_ranges = ["short", "medium", "long", "map"]

for time_range in time_ranges:
    for pref in team_prefixes:
        for side in sides:
            column_names += [
                f"{pref}_player_{i}_{side}_rating_avg_{time_range}" for i in range(5)
            ]
            column_names += [
                f"{pref}_player_{i}_{side}_rating_std_{time_range}" for i in range(5)
            ]
        column_names += [
            f"{pref}_player_{i}_maps_played_{time_range}" for i in range(5)
        ]


detailed_stats = ["kills", "hsKills", "assists", "deaths", "kast", "adr", "fkDiff"]

for pref in team_prefixes:
    for stat in detailed_stats:
        for side in sides:
            column_names += [f"{pref}_player_{i}_{side}_{stat}_avg" for i in range(5)]
            column_names += [f"{pref}_player_{i}_{side}_{stat}_std" for i in range(5)]
    column_names += [f"{pref}_player_{i}_maps_played_detailed" for i in range(5)]


column_names += [
    "team_one_win_num_matchup",
    "teams_played_num_matchup",
    "team_one_mean_rounds_matchup",
    "team_two_mean_rounds_matchup",
]

for pref in team_prefixes:
    for side in sides:
        column_names += [
            f"{pref}_player_{i}_{side}_rating_avg_matchup" for i in range(5)
        ]

column_names.append("winner")

for pref in team_prefixes:
    for side in sides + ["ot"]:
        column_names.append(f"{pref}_score_{side}")

column_names.append("map_id")
column_names.append("match_id")

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

thread_num = 80

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
                {"$sort": {"date": -1}},
                {"$skip": slice_size * i},
                {"$limit": slice_size},
            ]
        )
    )

    threading.Thread(
        target=process_maps,
        args=(maps_slice, frame_lock, history_lock, exit_lock, feature_data, i),
    ).start()
    time.sleep(1.5)

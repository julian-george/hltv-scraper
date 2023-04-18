import pymongo
import json
import atexit
import threading
import numpy as np
from datetime import datetime
from types import SimpleNamespace
from processing_helper import process_maps

client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["scraped-hltv"]
maps = db["maps"]

matrix_file_path = "./matrix.npy"
map_history_file_path = "./processed-maps.json"

# we use this so that the matrix is mutated, not replaced, within threads
feature_data = SimpleNamespace()

feature_data.matrix = np.empty([567, 0])
feature_data.history = set()

try:
    feature_data.matrix = np.load(matrix_file_path)
    print("Feature matrix loaded, shape:", feature_data.matrix.shape)
except:
    print(f"Unable to load matrix from {matrix_file_path}.")

try:
    map_history_file = open(map_history_file_path, "r")
    feature_data.history = set(json.loads(map_history_file.read()))
    map_history_file.close()
    print("Map history file loaded, length:", len(feature_data.history))
except:
    print(f"Unable to load map history from {map_history_file_path}")


def save_matrix():
    matrix_file = open(matrix_file_path, "wb+")
    np.save(matrix_file, feature_data.matrix)
    matrix_file.close()


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


atexit.register(save_matrix)
atexit.register(save_map_history)
atexit.register(print_process_rate)

num_maps = maps.count_documents({})

thread_num = 1

slice_size = np.ceil(num_maps / thread_num)

matrix_lock = threading.Lock()
history_lock = threading.Lock()

for i in range(thread_num):
    maps_slice = maps.aggregate(
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

    threading.Thread(
        target=process_maps,
        args=(maps_slice, matrix_lock, history_lock, feature_data),
    ).start()

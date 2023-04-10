import pymongo
import json
import atexit
import threading
import numpy as np
from processing_helper import process_maps

client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["scraped-hltv"]
maps = db["maps"]

matrix_file_path = "./matrix.npy"
map_history_file_path = "./processed-maps.json"

feature_matrix = np.empty([484, 0])
map_history = set()

try:
    feature_matrix = np.load(matrix_file_path)
    print("Feature matrix loaded, shape:", feature_matrix.shape)
except:
    print(f"Unable to load matrix from {matrix_file_path}.")

try:
    map_history_file = open(map_history_file_path, "r")
    map_history = set(json.loads(map_history_file.read()))
    map_history_file.close()
    print("Map history file loaded, length:", len(map_history))
except:
    print(f"Unable to load map history from {map_history_file_path}")


def save_matrix():
    matrix_file = open(matrix_file_path, "wb+")
    np.save(matrix_file, feature_matrix)
    matrix_file.close()


def save_map_history():
    map_history_file = open(map_history_file_path, "w+")
    map_history_file.write(json.dumps(list(map_history)))
    map_history_file.close()


atexit.register(save_matrix)
atexit.register(save_map_history)

num_maps = maps.count_documents({})

thread_num = 16

slice_size = np.ceil(num_maps / thread_num)

matrix_lock = threading.Lock()
history_lock = threading.Lock()


for i in range(thread_num):
    maps_slice = list(
        maps.find(
            {},
        )[(slice_size * i) : np.min((slice_size * (i + 1), num_maps))]
    )
    threading.Thread(
        target=process_maps,
        args=(maps_slice, matrix_lock, history_lock, feature_matrix, map_history),
    ).start()

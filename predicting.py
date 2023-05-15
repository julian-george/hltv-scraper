import pymongo
import pandas as pd
import tensorflow as tf
from processing_helper import generate_data_point
from learning_helper import process_frame

client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["scraped-hltv"]
unplayed_matches = db["unplayedmatches"]

model_name = "prediction_model"
model = tf.keras.models.load_model(model_name)

matches_to_predict = list(
    unplayed_matches.aggregate(
        [
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
    )
)

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

for match in matches_to_predict:
    for map_type in map_types:
        w = generate_data_point(match, played=False, map_type=map_type)
        processed_w = process_frame(pd.DataFrame([w]))[0]
        # processed_w.info(verbose=True)
        processed_w = processed_w.to_numpy()
        # print(processed_w.shape)
        prediction = model.predict(processed_w, verbose=False)
        print(match["title"], map_type, prediction)
    # break

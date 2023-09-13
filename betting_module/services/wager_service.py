import pymongo
import os

client = pymongo.MongoClient(os.environ["MONGODB_URI"])
db = client["scraped-hltv"]
unplayed_matches = db["unplayedmatches"]

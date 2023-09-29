import pymongo
import os
from dotenv import load_dotenv

load_dotenv()


client = pymongo.MongoClient(os.environ["MONGODB_URI"])
db = client["scraped-hltv"]
wagers = db["wagers"]


def wager_exists(wager_id):
    wager = wagers.find_one({"wagerId": wager_id})
    if wager == None:
        return False
    return wager


def insert_wager(wager):
    return wagers.insert_one(wager)


def update_wager_result(wager_id, new_result):
    return wagers.find_one_and_update(
        {"wagerId": wager_id}, {"$set": {"result": new_result}}
    )


def get_first_wager():
    return wagers.find_one()


def get_all_finished_wagers():
    return wagers.find(
        {"$and": [{"result": {"$ne": None}}, {"result": {"$ne": "UNFINISHED"}}]}
    ).sort("creationDate", pymongo.DESCENDING)

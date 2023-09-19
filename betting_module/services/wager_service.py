import pymongo
import os

client = pymongo.MongoClient(os.environ["MONGODB_URI"])
db = client["scraped-hltv"]
wagers = db["wagers"]


def wager_exists(wager_id):
    wager = wagers.find_one({"wagerId": wager_id})
    if wager == None:
        return False
    return wager


def insert_wager(wager):
    wagers.insert_one(wager)


def update_wager_result(wager_id, new_result):
    wagers.find_one_and_update({"wagerId": wager_id, "result": new_result})

import pymongo
import os

client = pymongo.MongoClient(os.environ["MONGODB_URI"])
db = client["scraped-hltv"]
unplayed_matches = db["unplayedmatches"]
matches = db["matches"]
maps = db["maps"]


def maps_to_examine():
    map_list = []
    all_unplayed = list(
        unplayed_matches.find({"played": True}).sort([("date", pymongo.DESCENDING)])
    )
    for unplayed in all_unplayed:
        hltv_id = unplayed["hltvId"]
        played_match = matches.find_one({"hltvId": hltv_id})
        if played_match:
            related_maps = list(maps.find({"matchId": played_match["hltvId"]}))
            for r_map in related_maps:
                map_list.append(r_map)
    return map_list

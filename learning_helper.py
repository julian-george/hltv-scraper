import numpy as np

delete_keywords = [
    "kills",
    "hsKills",
    "assists",
    "deaths",
    "kast",
    "adr",
    "fkDiff",
    "detailed",
    "score",
    "id",
    "std",
    "_medium",
    "_long",
    "map_date",
    "_bool",
]

# (adjusted) date rating 1.0 starts applying
truncation_date = 14.197


# prunes unwanted features using the data frame's column names
def process_frame(frame, label=None):
    y = None
    frame = frame[(frame["map_date"] > truncation_date)]
    # converts booleans to ints
    frame = frame * 1
    # ensuring label is an int so that decision tree viz works
    if label:
        frame = frame.astype({label: "int32"})
        y = np.array(frame["winner"].to_list()).astype(int)
    for column_name in frame.columns:
        to_delete = False
        if frame.dtypes[column_name] == object:
            frame = frame.astype({column_name: bool})
            frame = frame.astype({column_name: "int64"})
        if len([x for x in delete_keywords if x in column_name]) != 0:
            to_delete = True
        if to_delete:
            frame = frame.drop(column_name, axis=1)
    return frame, y

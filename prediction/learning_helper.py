import numpy as np
import pandas as pd
from copy import deepcopy
from processing_helper import quantize_time
from datetime import datetime


delete_keywords = ["map_id", "map_score", "stdev", "wonduels"]

# when rating 2.0 starts applying (March 2016)
truncation_date = 1456815600

# temp date
# truncation_date = quantize_time(datetime(year=2018, month=1, day=1))


# prunes unwanted features using the data frame's column names
def process_frame(frame, label=None):
    y = None
    frame = frame[(frame["map_date"] > truncation_date)]
    # converts booleans to ints
    frame = frame * 1
    # orders columns for consistency in matrix
    frame = frame.reindex(sorted(frame.columns), axis=1)
    # removing non-integer tie values
    # ensuring label is an int so that decision tree viz works
    sample_weights = deepcopy(frame["map_date"])
    sample_weights = (sample_weights - np.min(sample_weights)) / (
        np.max(sample_weights) - np.min(sample_weights)
    )
    sample_weights = sample_weights * 0.5
    sample_weights = sample_weights + 0.5
    if label:
        frame = frame.astype({label: "int32"})
        y = np.array(frame["winner"].to_list()).astype(int)
    for column_name in frame.columns:
        to_delete = False
        if frame.dtypes[column_name] == object:
            frame[column_name] = pd.to_numeric(frame[column_name], errors="coerce")
            frame = frame.astype({column_name: bool})
            frame = frame.astype({column_name: "int64"})

        if len([x for x in delete_keywords if x in column_name]) != 0:
            # print(column_nae)
            to_delete = True
        if to_delete:
            frame = frame.drop(column_name, axis=1)
    return frame, y, sample_weights

import pickle
import os

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import traceback
import numpy as np
import tensorflow as tf
import pandas as pd
import keras_tuner
from datetime import datetime

import tensorflow_model_optimization as tfmot
from tensorflow import keras
from sklearn.model_selection import train_test_split
from learning_helper import process_frame
from predicting import map_ids_to_examine

csv_folder = "learning_data/"

frame_file_path = csv_folder + "saved-frame.csv"
processed_frame_file_path = csv_folder + "processed-frame.csv"
examine_frame_file_path = csv_folder + "examine-frame.csv"
examine_ids_file_path = csv_folder + "examine-ids.csv"
matrix_file_path = csv_folder + "cached-matrix.npy"

feature_frame = None
feature_matrix = None
examine_frame = None
examine_ids = None

examine_matrix = None
X = None
y = None


label = "winner"


# taken from here: https://www.tensorflow.org/decision_forests/tutorials/dtreeviz_colab
def split_dataset(dataset, test_ratio=0.30, seed=1234):
    np.random.seed(seed)
    test_indices = np.random.rand(len(dataset)) < test_ratio
    return dataset[~test_indices], dataset[test_indices]


cached_frame = True

try:
    feature_frame = pd.read_csv(processed_frame_file_path, index_col=[0])
    examine_frame = pd.read_csv(examine_frame_file_path)
    examine_ids = pd.read_csv(examine_ids_file_path)
    print("Cached frames loaded")
except:
    print("Reprocessing frames")
    cached_frame = False
    feature_frame = pd.read_csv(frame_file_path, index_col=[0], low_memory=False)
    feature_frame = feature_frame.reindex(sorted(feature_frame.columns), axis=1)
    feature_frame = feature_frame.sort_values(by=["map_date"])
    # examine_ids = map_ids_to_examine()[:-1:2]
    examine_ids = []
    examine_frame = feature_frame[
        (feature_frame["map_id"].astype("int").isin(examine_ids))
    ]
    examine_ids = examine_frame["map_id"]

    examine_ids.to_csv(examine_ids_file_path)
    feature_frame = feature_frame[
        (feature_frame[label] != 0.5) & ~(feature_frame["map_id"].isin(examine_ids))
    ].dropna()
    (feature_frame, y, sample_weights) = process_frame(feature_frame, label)
    (examine_frame, examine_y, _) = process_frame(examine_frame, label)
    examine_frame.to_csv(examine_frame_file_path)
    print("Feature frame loaded, shape:", feature_frame.shape)
    feature_frame.to_csv(processed_frame_file_path)

try:
    if not cached_frame:
        raise Exception
    feature_matrix = np.load(matrix_file_path)
    print("Cached matrix loaded")
except:
    print("Rebuilding matrix")
    try:
        feature_matrix = np.hstack(
            [
                feature_frame.drop(label, axis=1).to_numpy(),
                np.array([sample_weights]).T,
                np.array([y]).T,
            ]
        )
        np.save(matrix_file_path, feature_matrix)
    except Exception as e:
        print(f"ERROR: Unable to load frame from {frame_file_path}.", e)
        traceback.print_exc()

print("Feature matrix processed, shape:", feature_matrix.shape)

try:
    examine_ids = pd.read_csv(examine_ids_file_path, index_col=[0])
except:
    print("Unable to get examine ids")

clfs = []

y = feature_matrix[:, -1]
X = feature_matrix[:, :-1]

X_train = X
y_train = y

num_test_sets = 6
test_set_size = 2

test_sets = []

date_column = list(feature_frame.columns).index("map_date")

for i in range(num_test_sets):
    X_train, X_test, y_train, y_test = train_test_split(
        X_train, y_train, test_size=test_set_size, shuffle=False
    )
    print(datetime.fromtimestamp(X_test[0, date_column]))
    test_sets.append(
        (
            X_test[:, :-1],
            y_test,
            datetime.fromtimestamp(X_test[0, date_column]),
        )
    )


X_train, X_test, y_train, y_test = train_test_split(
    X_train, y_train, test_size=1, shuffle=True
)

X_train_weights = X_train[:, -1]
X_train = X_train[:, :-1]

X_test = X_test[:, :-1]

normalization_layer = keras.layers.Normalization()
normalization_layer.adapt(X_train)

num_features = X_train.shape[1]


def build_model(hp=None, normalize=True):
    default_layer_size_diff = 30
    layer_size_diff = (
        hp.Choice(
            "layer_size_diff",
            [
                10,
                20,
                30,
            ],
        )
        if hp
        else default_layer_size_diff
    )
    layer_size = num_features + layer_size_diff

    default_layer_num = 6
    layer_num = (
        hp.Choice(
            "layer_num",
            [
                2,
                4,
                6,
            ],
        )
        if hp
        else default_layer_num
    )

    activation_function = "relu"

    layer_list = []

    if normalize:
        layer_list.append(normalization_layer)
    else:
        layer_list.append(keras.layers.InputLayer(num_features))

    for l_i in range(layer_num):
        layer_list.append(keras.layers.Dense(layer_size, activation_function))

    layer_list.append(keras.layers.Dense(2, activation="softmax"))
    model = keras.Sequential(layer_list)
    model.build()
    default_learning_rate = 0.0005
    # learning_rate = default_learning_rate
    learning_rate = (
        hp.Choice(
            "learning_rate",
            [0.001, 0.0005, 0.0001, 0.00005, 0.00001],
        )
        if hp
        else default_learning_rate
    )
    opt = keras.optimizers.Adam(learning_rate=learning_rate)
    model.compile(
        optimizer=opt,
        loss=keras.losses.sparse_categorical_crossentropy,
        metrics=["accuracy"],
        weighted_metrics=[
            keras.losses.sparse_categorical_crossentropy,
            keras.metrics.sparse_categorical_accuracy,
        ],
    )
    model.summary()

    return model


# normalized_X = normalization_layer(X_train)
normalized_X = X_train
batch_size = 32
epoch_num = 32
validation_split = 0.25
# stop_early = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3)
scores = []
model = None
csv_logger = tf.keras.callbacks.CSVLogger(csv_folder + "metrics.csv")
print(normalized_X.shape[1], num_features)
for i in range(1):
    model = build_model()
    history = model.fit(
        normalized_X,
        y_train,
        batch_size=batch_size,
        validation_split=validation_split,
        epochs=epoch_num,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3),
            tf.keras.callbacks.CSVLogger(csv_folder + "metrics.csv"),
        ],
        # sample_weight=X_train_wights,
    )
    for i, test_set in enumerate(test_sets):
        print(test_set[2])
        print(test_set[1])
        pd.DataFrame(test_set[0]).to_csv(csv_folder + f"w_{i}_learning.csv")
        scores.append(
            round(model.evaluate(test_set[0], test_set[1], batch_size=1)[1], 3)
        )
        print(np.round(model.predict(test_set[0]), 3), test_set[1])

print(np.mean(scores))

# model.evaluate(_frame.drop(label, axis=1), examine_frame[label], batch_size=1)
# for i, data_point in examine_frame.drop(label, axis=1).iterrows():
#     print(examine_ids["map_id"][i], model.predict(np.array([data_point.to_numpy()])))

full_examine = pd.concat([examine_ids, examine_frame], axis=1)

model_path = "./prediction_model"

print("Saving Model")
model.save(model_path)

# hyperparam tuning

# tuner = keras_tuner.Hyperband(build_model, objective="val_loss")
# tuner.search(
#     X_train,
#     y_train,
#     epochs=epoch_num,
#     batch_size=batch_size,
#     validation_split=validation_split,
#     callbacks=[tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3)],
#     sample_weight=X_train_weights,
# )
# best_model = tuner.get_best_models()[0]
# print("Saving Tuned Model")
# best_model.save(model_path)


# base_line_loss = np.min(history.history["val_loss"])
# loss_threshold = 0.005
# cols_to_prune = []
# for i in range(X_train.shape[1]):
#     pruned_X = np.delete(X_train, i, axis=1)
#     pruned_history = build_model().fit(
#         normalized_X,
#         y_train,
#         batch_size=batch_size,
#         validation_split=validation_split,
#         epochs=epoch_num,
#         callbacks=[stop_early],
#     )
#     if np.min(pruned_history.history["val_loss"]) < base_line_loss - loss_threshold:
#         print("Prune index", i)
#         cols_to_prune.append(i)

# print("to prune", cols_to_prune)

# prune_low_magnitude = tfmot.sparsity.keras.prune_low_magnitude

# num_points = normalized_X.shape[0] * (1 - validation_split)
# end_step = np.ceil(num_points / batch_size).astype(np.int32) * epoch_num

# # # Define model for pruning.
# pruning_params = {
#     "pruning_schedule": tfmot.sparsity.keras.PolynomialDecay(
#         initial_sparsity=0.5, final_sparsity=0.9, begin_step=0, end_step=end_step
#     ),
# }

# callbacks = [
#     tfmot.sparsity.keras.UpdatePruningStep(),
# ]

# normalized_X = normalization_layer(X_train)

# model_for_pruning = build_model(normalize=False)

# model_for_pruning.fit(
#     normalized_X,
#     y_train,
#     batch_size=batch_size,
#     epochs=epoch_num,
#     validation_split=validation_split,
#     callbacks=callbacks,
#     sample_weight=X_train_weights,
# )

# model_for_pruning = prune_low_magnitude(model_for_pruning, **pruning_params)

# # # `prune_low_magnitude` requires a recompile.
# model_for_pruning.compile(
#     optimizer="adam",
#     loss=tf.keras.losses.SparseCategoricalCrossentropy(),
#     metrics=[
#         keras.metrics.SparseCategoricalAccuracy(name="acc"),
#     ],
#     weighted_metrics=[
#         keras.losses.sparse_categorical_crossentropy,
#         keras.metrics.sparse_categorical_accuracy,
#     ],
# )

# model_for_pruning.summary()


# model_for_pruning.fit(
#     normalized_X,
#     y_train,
#     batch_size=batch_size,
#     epochs=epoch_num * 2,
#     validation_split=validation_split,
#     callbacks=callbacks,
#     sample_weight=X_train_weights,
# )

# model_for_pruning.save(model_path)

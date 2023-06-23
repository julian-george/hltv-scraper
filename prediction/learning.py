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


frame_file_path = "saved-frame.csv"
examine_frame_file_path = "examine-frame.csv"
examine_ids_file_path = "examine-ids.csv"
matrix_file_path = "cached-matrix.npy"

feature_frame = None
feature_matrix = None
examine_frame = None
examine_ids = map_ids_to_examine()[:-30:2]

examine_matrix = None
X = None
y = None


label = "winner"


# taken from here: https://www.tensorflow.org/decision_forests/tutorials/dtreeviz_colab
def split_dataset(dataset, test_ratio=0.30, seed=1234):
    np.random.seed(seed)
    test_indices = np.random.rand(len(dataset)) < test_ratio
    return dataset[~test_indices], dataset[test_indices]


try:
    feature_matrix = np.load(matrix_file_path)
    print("matrix loaded")
except:
    print("No feature matrix found, building from data frame")
    try:
        # low_memory=False to get rid of mixed-type warning
        # TODO: move all of this to own function to allow for easier frame import
        feature_frame = pd.read_csv(frame_file_path, index_col=[0], low_memory=False)
        feature_frame = feature_frame.reindex(sorted(feature_frame.columns), axis=1)
        feature_frame = feature_frame.sort_values(by=["map_date"])
        feature_frame.to_csv("sorted_saved.csv")
        examine_frame = feature_frame[
            (feature_frame["map_id"].astype("int").isin(examine_ids))
        ]
        examine_ids = examine_frame["map_id"]

        examine_ids.to_csv(examine_ids_file_path)
        feature_frame = feature_frame[
            (feature_frame[label] != 0.5) & ~(feature_frame["map_id"].isin(examine_ids))
        ].dropna()
        print("Feature frame loaded, shape:", feature_frame.shape)
        (feature_frame, y, sample_weights) = process_frame(feature_frame, label)
        (examine_frame, examine_y, _) = process_frame(examine_frame, label)
        examine_frame.to_csv(examine_frame_file_path)

        # feature_frame.info(verbose=True)
        feature_frame.drop(label, axis=1).to_csv("test2.csv")
        # with open("f.txt", "w") as f:
        #     f.write("\n".join(sorted(list(feature_frame.columns))))
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

num_test_sets = 30
test_set_size = 245

test_sets = []

date_column = list(feature_frame.columns).index("map_date")

print(feature_frame.iloc[1])


for i in range(num_test_sets):
    X_train, X_test, y_train, y_test = train_test_split(
        X_train, y_train, test_size=245, shuffle=False
    )
    print(X_test[0, date_column])
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

# # Split into training and test sets
# rf_train_pd, rf_test_pd = split_dataset(feature_frame)
# print(
#     f"{len(rf_train_pd)} examples in training, {len(rf_test_pd)} examples for testing."
# )

# classes = list(feature_frame[label].unique())


# # Convert to tensorflow data sets
# rf_train = tfdf.keras.pd_dataframe_to_tf_dataset(rf_train_pd, label=label)
# rf_test = tfdf.keras.pd_dataframe_to_tf_dataset(rf_test_pd, label=label)

# # Train a Random Forest model.
# rf_model = tfdf.keras.RandomForestModel(verbose=0, random_seed=1234)
# rf_model.fit(rf_train)

# rf_model.compile(metrics=["accuracy"])
# rf_model.evaluate(rf_test, return_dict=True, verbose=0)

# # Tell dtreeviz about training data and model
# rf_features = [f.name for f in rf_model.make_inspector().features()]
# viz_rf_model = dtreeviz.model(
#     rf_model,
#     tree_index=3,
#     X_train=rf_train_pd[rf_features],
#     y_train=rf_train_pd[label],
#     feature_names=rf_features,
#     target_name=label,
#     class_names=[0, 1],
# )
# viz_rf_model.view(scale=1.2)


normalization_layer = keras.layers.Normalization()
normalization_layer.adapt(X_train)

num_features = X_train.shape[1]


def build_model(hp=None, normalize=True):
    default_layer_size_diff = 0
    layer_size_diff = (
        hp.Choice(
            "layer_size_diff",
            [
                -20,
                -10,
                0,
                10,
                20,
            ],
        )
        if hp
        else default_layer_size_diff
    )
    layer_size = num_features + layer_size_diff

    default_layer_num = 4
    layer_num = (
        hp.Choice(
            "layer_num",
            [
                2,
                3,
                4,
                5,
                6,
                7,
                8,
                10,
                12,
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
    default_learning_rate = 0.001
    # learning_rate = default_learning_rate
    learning_rate = (
        hp.Choice(
            "learning_rate",
            [
                0.005,
                0.0025,
                0.001,
                0.0005,
            ],
        )
        if hp
        else default_learning_rate
    )
    opt = keras.optimizers.Adam(learning_rate=learning_rate)
    model.compile(
        optimizer=opt,
        loss="sparse_categorical_crossentropy",
        metrics=[
            keras.metrics.SparseCategoricalAccuracy(name="acc"),
            # keras.metrics.F1Score(),
        ],
        weighted_metrics=[
            keras.losses.sparse_categorical_crossentropy,
            keras.metrics.sparse_categorical_accuracy,
        ],
    )
    model.summary()

    return model


# normalized_X = normalization_layer(X_train)
normalized_X = X_train
print(examine_ids["map_id"])
batch_size = 32
epoch_num = 32
validation_split = 0.25
# stop_early = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3)
scores = []
model = None
csv_logger = tf.keras.callbacks.CSVLogger("metrics.csv")
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
            tf.keras.callbacks.EarlyStopping(monitor="val_acc", patience=3),
            tf.keras.callbacks.CSVLogger("metrics.csv"),
        ],
        sample_weight=X_train_weights,
    )
    for test_set in test_sets:
        print(test_set[2])
        scores.append(model.evaluate(test_set[0], test_set[1], batch_size=1)[1])
print(np.mean(scores))

model.evaluate(examine_frame.drop(label, axis=1), examine_frame[label], batch_size=1)
# for i, data_point in examine_frame.drop(label, axis=1).iterrows():
#     print(examine_ids["map_id"][i], model.predict(np.array([data_point.to_numpy()])))

full_examine = pd.concat([examine_ids, examine_frame], axis=1)

model_path = "./prediction_model"

print("Saving Model")
model.save(model_path)

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
# print("Saving Model")
# best_model.save(model_path)


# scaler = RobustScaler()
# scaler.fit(X_train)
# X_train = scaler.transform(X_train)
# X_test = scaler.transform(X_test)
# clf = MLPClassifier(
#     random_state=1,
#     max_iter=200,
#     activation="relu",
#     early_stopping=True,
#     hidden_layer_sizes=(250, 250, 250, 250),
# ).fit(X_train, y_train)
# clfs.append(clf)


# classifier_labels = [
#     "Winner T Score",
#     "Winner CT Score",
#     "Winner OT Score",
#     "Loser T Score",
#     "Loser CT Score",
#     "Loser OT Score",
# ]

# for i in range(6):
#     print("Scraping", i)
#     X = feature_matrix[:, :-8]
#     y = feature_matrix[:, -8 + i].T
#     X_train, X_test, y_train, y_test = train_test_split(X, y)

#     scaler = StandardScaler()
#     scaler.fit(X_train)
#     X_train = scaler.transform(X_train)
#     X_test = scaler.transform(X_test)
#     clf = MLPRegressor(random_state=1, max_iter=500).fit(X_train, y_train)
#     # clf.predict_proba(X_test[:1])
#     clf.predict(X_test)
#     print(classifier_labels[i], clf.score(X_test, y_test))
#     clfs.append(clf)

# file_titles = [
#     "win_t_model.sav",
#     "win_ct_model.sav",
#     "win_ot_model.sav",
#     "lose_t_model.sav",
#     "lose_ct_model.sav",
#     "lose_ot_model.sav",
# ]

for i in range(len(clfs)):
    pickle.dump(clfs[i], open(f"model-{i}.sav", "wb+"))

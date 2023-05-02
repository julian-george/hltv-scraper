import pickle
import numpy as np
import tensorflow as tf
import keras_tuner
import tensorflow_decision_forests as tfdf
import pandas as pd
from scipy import stats as st
from tensorflow import keras
from sklearn.neural_network import MLPRegressor, MLPClassifier
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler, StandardScaler
import tensorflow_model_optimization as tfmot


# feature_matrix = np.empty([517, 0])
num_ending_cols = 9

frame_file_path = "frame.csv"

try:
    feature_matrix = pd.read_csv(frame_file_path).to_numpy()
    print("Feature matrix loaded, shape:", feature_matrix.shape)
except:
    print(f"Unable to load matrix from {frame_file_path}.")

# (adjusted) date rating 1.0 starts applying
truncation_date = 14.197

to_prune = []

for data_row in feature_matrix:
    if data_row[0] <= truncation_date:
        to_prune.append(False)
    else:
        to_prune.append(True)

feature_matrix = feature_matrix[to_prune]

feature_matrix.tofile("matrix.csv", sep=",")

print(feature_matrix[120, :])

# matchup
#  win rates
# feature_matrix = np.delete(feature_matrix, slice(619, 621), axis=1)
#  avg round num
feature_matrix = np.delete(feature_matrix, slice(617, 619), axis=1)
#  player ratings
feature_matrix = np.delete(feature_matrix, slice(598, 617), axis=1)
# event
#  win rates
feature_matrix = np.delete(feature_matrix, slice(593, 597), axis=1)
#  round nums
# feature_matrix = np.delete(feature_matrix, slice(591, 593), axis=1)
#  player ratings
feature_matrix = np.delete(feature_matrix, slice(571, 591), axis=1)
# detailed stats
feature_matrix = np.delete(feature_matrix, slice(281, 571), axis=1)
# # long term
feature_matrix = np.delete(feature_matrix, slice(231, 281), axis=1)
# # medium term
feature_matrix = np.delete(feature_matrix, slice(181, 231), axis=1)
# # short term
# feature_matrix = np.delete(feature_matrix, slice(131, 181), axis=1)
#  num_valid
feature_matrix = np.delete(feature_matrix, slice(131, 181, 5), axis=1)
#  stdev
feature_matrix = np.delete(feature_matrix, slice(132, 171, 2), axis=1)
# map stats
# feature_matrix = np.delete(feature_matrix, slice(81, 131), axis=1)
#  num_valid
feature_matrix = np.delete(feature_matrix, slice(81, 131, 5), axis=1)
#  stdev
feature_matrix = np.delete(feature_matrix, slice(82, 121, 2), axis=1)
# non- avg round win stats
#  map
feature_matrix = np.delete(feature_matrix, slice(79, 81), axis=1)
#  avg rounds
feature_matrix = np.delete(feature_matrix, slice(77, 79), axis=1)
feature_matrix = np.delete(feature_matrix, slice(75, 77), axis=1)
#  general
feature_matrix = np.delete(feature_matrix, slice(73, 75), axis=1)
#  avg rounds
feature_matrix = np.delete(feature_matrix, slice(71, 73), axis=1)
feature_matrix = np.delete(feature_matrix, slice(69, 71), axis=1)
# # duel map
feature_matrix = np.delete(feature_matrix, slice(19, 69), axis=1)
# # map vector
feature_matrix = np.delete(feature_matrix, slice(8, 19), axis=1)
# team rankings
# feature_matrix = np.delete(feature_matrix, slice(6, 8), axis=1)
# # team rankings std
feature_matrix = np.delete(feature_matrix, 5, axis=1)
# # team rankings mean
feature_matrix = np.delete(feature_matrix, 4, axis=1)
# online
feature_matrix = np.delete(feature_matrix, 3, axis=1)
# # prize pool
feature_matrix = np.delete(feature_matrix, 2, axis=1)
# numMaps
feature_matrix = np.delete(feature_matrix, 1, axis=1)
# # date
feature_matrix = np.delete(feature_matrix, 0, axis=1)


clfs = []

X = feature_matrix[:, :-num_ending_cols]
y = feature_matrix[:, -num_ending_cols].T


X_train, X_test, y_train, y_test = train_test_split(X, y)

# # Train a Random Forest model.
# model = tfdf.keras.RandomForestModel()
# model.fit(X_train, y_train)

# # Summary of the model structure.
# model.summary()

# # Evaluate the model.
# model.evaluate(X_test, y_test)

num_features = feature_matrix.shape[1]


def build_model(hp=None):
    default_layer_size_diff = 20
    layer_size_diff = (
        hp.Choice("layer_size_diff", [-30, -20, -10, 0, 10, 20, 30])
        if hp
        else default_layer_size_diff
    )
    layer_size = num_features + layer_size_diff

    default_layer_num = 4
    layer_num = (
        hp.Choice("layer_num", [3, 4, 5, 6, 7, 8, 9, 10]) if hp else default_layer_num
    )

    default_activation = "relu"
    activation_function = (
        hp.Choice("activation", ["relu", "tanh", "selu", "leaky_relu"])
        if hp
        else default_activation
    )

    inputs = keras.Input((num_features - num_ending_cols))
    x = inputs

    for l_i in range(layer_num):
        x = keras.layers.Dense(layer_size, activation_function)(x)

    outputs = keras.layers.Dense(2, activation="softmax")(x)
    model = keras.Model(inputs, outputs)
    model.summary()
    opt = keras.optimizers.Adam(learning_rate=0.005)
    model.compile(
        optimizer=opt,
        loss="sparse_categorical_crossentropy",
        metrics=[keras.metrics.SparseCategoricalAccuracy(name="acc")],
    )

    return model


normalization_layer = keras.layers.Normalization()
normalization_layer.adapt(X_train)

normalized_X = normalization_layer(X_train)
# normalized_X = X

batch_size = 64
epoch_num = 20
validation_split = 0.1
stop_early = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3)
scores = []
for i in range(3):
    model = build_model()
    history = model.fit(
        normalized_X,
        y_train,
        batch_size=batch_size,
        validation_split=validation_split,
        epochs=epoch_num,
        callbacks=[stop_early],
    )
    scores.append(model.evaluate(normalization_layer(X_test), y_test)[1])
print(np.mean(scores))

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

# num_images = X.shape[0] * (1 - validation_split)
# end_step = np.ceil(num_images / batch_size).astype(np.int32) * epoch_num

# # Define model for pruning.
# pruning_params = {
#     "pruning_schedule": tfmot.sparsity.keras.PolynomialDecay(
#         initial_sparsity=0.5, final_sparsity=0.8, begin_step=0, end_step=end_step
#     )
# }

# model_for_pruning = prune_low_magnitude(model, **pruning_params)

# # `prune_low_magnitude` requires a recompile.
# model_for_pruning.compile(
#     optimizer="adam",
#     loss=tf.keras.losses.SparseCategoricalCrossentropy(),
#     metrics=["accuracy"],
# )

# model_for_pruning.summary()

# callbacks = [
#     tfmot.sparsity.keras.UpdatePruningStep(),
# ]

# model_for_pruning.fit(
#     X,
#     y,
#     batch_size=batch_size,
#     epochs=epoch_num,
#     validation_split=validation_split,
#     callbacks=callbacks,
# )

# tuner = keras_tuner.Hyperband(build_model, objective="loss")
# tuner.search(
#     X,
#     y,
#     epochs=epoch_num,
#     batch_size=batch_size,
#     callbacks=[stop_early],
# )
# best_model = tuner.get_best_models()[0]


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

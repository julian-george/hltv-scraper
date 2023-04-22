import pickle
import numpy as np
import tensorflow as tf
import keras_tuner
import tensorflow_decision_forests as tfdf
from tensorflow import keras
from sklearn.neural_network import MLPRegressor, MLPClassifier
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler, StandardScaler

# feature_matrix = np.empty([517, 0])
num_ending_cols = 9

matrix_file_path = "./matrix.npy"

try:
    feature_matrix = np.load(matrix_file_path)
    print("Feature matrix loaded, shape:", feature_matrix.shape)
except:
    print(f"Unable to load matrix from {matrix_file_path}.")


feature_matrix = feature_matrix.T
# (adjusted) date rating 1.0 starts applying
truncation_date = 14.197

to_prune = []

for data_row in feature_matrix:
    if data_row[0] <= truncation_date:
        to_prune.append(False)
    else:
        to_prune.append(True)

feature_matrix = feature_matrix[to_prune]

print(feature_matrix.shape)

# detailed stats
feature_matrix = np.delete(feature_matrix, slice(277, 567), axis=1)
# long term
feature_matrix = np.delete(feature_matrix, slice(227, 277), axis=1)
# medium term
feature_matrix = np.delete(feature_matrix, slice(177, 227), axis=1)
# short term
# feature_matrix = np.delete(feature_matrix, slice(127, 177), axis=1)
# duel map
# feature_matrix = np.delete(feature_matrix, slice(19, 69), axis=1)
# team rankings std
feature_matrix = np.delete(feature_matrix, 5, axis=1)
# team rankings mean
# feature_matrix = np.delete(feature_matrix, 4, axis=1)
# prize pool
feature_matrix = np.delete(feature_matrix, 2, axis=1)
# date
feature_matrix = np.delete(feature_matrix, 0, axis=1)

print(feature_matrix.shape)

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

    default_layer_num = 6
    layer_num = (
        hp.Choice("layer_num", [3, 4, 5, 6, 7, 8, 9, 10]) if hp else default_layer_num
    )

    default_activation = "leaky_relu"
    activation_function = (
        hp.Choice("activation", ["relu", "tanh", "selu", "leaky_relu"])
        if hp
        else default_activation
    )

    inputs = keras.Input((num_features - num_ending_cols))
    x = keras.layers.Normalization()(inputs)

    for l_i in range(layer_num):
        x = keras.layers.Dense(layer_size, activation_function)(x)

    outputs = keras.layers.Dense(2, activation="softmax")(x)
    model = keras.Model(inputs, outputs)
    model.summary()

    model.compile(
        optimizer="adam",
        loss="sparse_categorical_crossentropy",
        metrics=[keras.metrics.SparseCategoricalAccuracy(name="acc")],
    )

    print("Fit on NumPy data")
    return model


batch_size = 32
epoch_num = 250
stop_early = tf.keras.callbacks.EarlyStopping(monitor="loss", patience=5)
history = build_model().fit(
    X,
    y,
    batch_size=batch_size,
    epochs=300,
    callbacks=[stop_early],
)

# tuner = keras_tuner.Hyperband(build_model, objective="loss")
# tuner.search(
#     X,
#     y,
#     epochs=epoch_num,
#     batch_size=batch_size,
#     callbacks=[stop_early],
# )
# best_model = tuner.get_best_models()[0]


scaler = RobustScaler()
scaler.fit(X_train)
X_train = scaler.transform(X_train)
X_test = scaler.transform(X_test)
clf = MLPClassifier(
    random_state=1,
    max_iter=200,
    activation="relu",
    early_stopping=True,
    hidden_layer_sizes=(250, 250, 250, 250),
).fit(X_train, y_train)
clfs.append(clf)


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

import pickle
import os

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import traceback
import numpy as np
import tensorflow as tf
import pandas as pd
from tensorflow import keras
from sklearn.model_selection import train_test_split
from learning_helper import process_frame


frame_file_path = "saved-frame.csv"
matrix_file_path = "cached-matrix.npy"

feature_matrix = None
feature_frame = None
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
except:
    print("No feature matrix found, building from data frame")
    try:
        # low_memory=False to get rid of mixed-type warning
        feature_frame = pd.read_csv(frame_file_path, index_col=[0], low_memory=False)
        feature_frame = feature_frame[(feature_frame[label] != 0.5)]
        print("Feature frame loaded, shape:", feature_frame.shape)
        (feature_frame, y) = process_frame(feature_frame, label)
        # feature_frame.info(verbose=True)
        feature_matrix = np.hstack(
            [feature_frame.drop("winner", axis=1).to_numpy(), np.array([y]).T]
        )
        np.save(matrix_file_path, feature_matrix)
    except Exception as e:
        print(f"ERROR: Unable to load frame from {frame_file_path}.", e)
        traceback.print_exc()

print("Feature matrix processed, shape:", feature_matrix.shape)


clfs = []

X = feature_matrix[:, :-1]
y = feature_matrix[:, -1]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.1)

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

num_features = X.shape[1]

normalization_layer = keras.layers.Normalization()
normalization_layer.adapt(X_train)


def build_model(hp=None):
    default_layer_size_diff = 30
    layer_size_diff = (
        hp.Choice("layer_size_diff", [-30, -20, -10, 0, 10, 20, 30])
        if hp
        else default_layer_size_diff
    )
    layer_size = num_features + layer_size_diff

    default_layer_num = 3
    layer_num = (
        hp.Choice("layer_num", [3, 4, 5, 6, 7, 8, 9, 10]) if hp else default_layer_num
    )

    default_activation = "relu"
    activation_function = (
        hp.Choice("activation", ["relu", "tanh", "selu", "leaky_relu"])
        if hp
        else default_activation
    )

    layer_list = []

    layer_list.append(normalization_layer)
    layer_list.append(keras.layers.Dense(num_features, activation_function))

    for l_i in range(layer_num - 1):
        layer_list.append(keras.layers.Dense(layer_size, activation_function))

    layer_list.append(keras.layers.Dense(2, activation="softmax"))
    model = keras.Sequential(layer_list)
    model.summary()
    opt = keras.optimizers.Adam(learning_rate=0.001)
    model.compile(
        optimizer=opt,
        loss="sparse_categorical_crossentropy",
        metrics=[keras.metrics.SparseCategoricalAccuracy(name="acc")],
    )

    return model


# normalized_X = normalization_layer(X_train)
normalized_X = X_train

batch_size = 64
epoch_num = 20
validation_split = 0.1
stop_early = tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3)
scores = []
model = None
for i in range(1):
    model = build_model()
    history = model.fit(
        normalized_X,
        y_train,
        batch_size=batch_size,
        validation_split=validation_split,
        epochs=epoch_num,
        callbacks=[stop_early],
    )
    scores.append(model.evaluate(X_test, y_test)[1])
print(np.mean(scores))

print(np.array([X_test[0]]).shape)

model_path = "prediction_model"

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

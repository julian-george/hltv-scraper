import pickle
import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# feature_matrix = np.empty([517, 0])

matrix_file_path = "./matrix.npy"

try:
    feature_matrix = np.load(matrix_file_path)
    print("Feature matrix loaded, shape:", feature_matrix.shape)
except:
    print(f"Unable to load matrix from {matrix_file_path}.")


feature_matrix = feature_matrix.T

for i in range(feature_matrix.shape[0]):
    print(feature_matrix[i])
    if np.nan in feature_matrix[i]:
        print(feature_matrix[i])
        feature_matrix = np.delete(feature_matrix, i, 0)


# 6-array, ordered:
#  winning t side, winning ct, winning ot
#  losing t side, losing ct, losing ot
clfs = []

classifier_labels = [
    "Winner T Score",
    "Winner CT Score",
    "Winner OT Score",
    "Loser T Score",
    "Loser CT Score",
    "Loser OT Score",
]

for i in range(6):
    print("Scraping", i)
    X = feature_matrix[:, :-8]
    y = feature_matrix[:, -8 + i].T
    X_train, X_test, y_train, y_test = train_test_split(X, y)

    scaler = StandardScaler()
    scaler.fit(X_train)
    X_train = scaler.transform(X_train)
    X_test = scaler.transform(X_test)
    clf = MLPRegressor(random_state=1, max_iter=100).fit(X_train, y_train)
    # clf.predict_proba(X_test[:1])
    clf.predict(X_test)
    print(classifier_labels[i], clf.score(X_test, y_test))
    clfs.append(clf)

file_titles = [
    "win_t_model.sav",
    "win_ct_model.sav",
    "win_ot_model.sav",
    "lose_t_model.sav",
    "lose_ct_model.sav",
    "lose_ot_model.sav",
]

for i in range(6):
    pickle.dump(clfs[i], open(file_titles[i], "wb+"))

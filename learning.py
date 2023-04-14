import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split

# feature_matrix = np.empty([517, 0])

matrix_file_path = "./matrix.npy"

# try:
feature_matrix = np.load(matrix_file_path)
print("Feature matrix loaded, shape:", feature_matrix)
# except:
#     print(f"Unable to load matrix from {matrix_file_path}.")

print(feature_matrix.shape)

# X_train, X_test, y_train, y_test = train_test_split(, y, stratify=y,random_state=1)
# clf = MLPClassifier(random_state=1, max_iter=300).fit(X_train, y_train)
# clf.predict_proba(X_test[:1])
# clf.predict(X_test[:5, :])
# clf.score(X_test, y_test)

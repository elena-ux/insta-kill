import numpy as np
import pytest

from app.retrieval import cosine_similarity, stable_top_k


def test_direction_zero_vectors_and_no_mutation():
    q = np.array([2.0, 0.0])
    corpus = np.array([[5.0, 0.0], [0.0, 0.0], [-3.0, 0.0], [0.0, 2.0]])
    before = corpus.copy()
    np.testing.assert_allclose(cosine_similarity(q, corpus), [1, 0, -1, 0])
    np.testing.assert_allclose(cosine_similarity(np.zeros(2), corpus), np.zeros(4))
    np.testing.assert_array_equal(before, corpus)
    assert cosine_similarity(q, np.empty((0, 2))).shape == (0,)


def test_top_k_exact_ties_and_limits():
    assert stable_top_k([0.8, 0.9, 0.9, 0.8], [21, 12, 7, 3], 3).tolist() == [2, 1, 3]
    assert stable_top_k([1], [4], 50).tolist() == [0]
    assert stable_top_k([], [], 5).tolist() == []
    assert stable_top_k([1], [4], 0).tolist() == []


@pytest.mark.parametrize("query,corpus", [([1], [[1, 2]]), ([float("nan")], [[1]]), ([[1]], [[1]])])
def test_invalid_embeddings(query, corpus):
    with pytest.raises(ValueError):
        cosine_similarity(query, corpus)

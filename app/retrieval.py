"""Pure NumPy retrieval: no HTTP, storage, or encoder calls."""

import numpy as np


def cosine_similarity(query_vector, corpus_vectors):
    """Compare direction; a zero query or corpus row receives score zero."""
    query = np.asarray(query_vector, dtype=float)
    corpus = np.asarray(corpus_vectors, dtype=float)
    if query.ndim != 1 or corpus.ndim != 2 or corpus.shape[1] != query.size:
        raise ValueError("Expected one query vector and a matching corpus matrix.")
    if not np.isfinite(query).all() or not np.isfinite(corpus).all():
        raise ValueError("Embeddings must contain finite numbers.")
    # Fiecare rând din corpus reprezintă vectorul unei postări.
    dot_products = corpus @ query
    query_length = np.linalg.norm(query)
    post_lengths = np.linalg.norm(corpus, axis=1)
    denominators = post_lengths * query_length

    # Dacă un vector are lungimea zero, scorul lui rămâne zero.
    scores = np.divide(
        dot_products,
        denominators,
        out=np.zeros(corpus.shape[0]),
        where=denominators != 0,
    )
    return np.clip(scores, -1.0, 1.0)


def stable_top_k(scores, post_ids, k):
    """Return row indices by score descending, then post ID ascending."""
    values = np.asarray(scores, dtype=float)
    ids = np.asarray(post_ids)
    if values.ndim != 1 or ids.ndim != 1 or len(values) != len(ids):
        raise ValueError("Scores and IDs must be aligned one-dimensional arrays.")
    if not np.isfinite(values).all() or not isinstance(k, int) or k < 0:
        raise ValueError("Scores must be finite and k must be a nonnegative integer.")
    # lexsort folosește ultima cheie prima: scor descrescător, apoi ID crescător.
    sorted_indices = np.lexsort((ids, -values))
    return sorted_indices[:k]

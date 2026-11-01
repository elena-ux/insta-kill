# Week 3 — Semantic search

I used `all-MiniLM-L6-v2` on CPU to convert text into vectors.
I did not train a new model.

- [`cosine_similarity`](../app/retrieval.py) compares the query vector with the post vectors. Zero vectors receive a score of 0.
- [`stable_top_k`](../app/retrieval.py) selects the top results: score descending, then ID ascending for ties.
- [`SearchService.search`](../app/application/search.py) reads posts, calculates scores, and builds the response.

`GET /search?q=inexpensive%20supper&limit=5` searches by meaning.
`mode=keyword` compares shared words.

The encoder loads the model on the first semantic search and reuses it.
Timing is measured separately in [`evaluate_search.py`](../scripts/evaluate_search.py).
The script measures imports, model loading, and corpus encoding before the comparisons.
Request timings use the loaded model and include recalculating post vectors.

On the 30 synthetic posts, semantic search finds the affordable restaurant
without shared words with the query. However, it ranks an expensive restaurant
above it and can ignore negation. Similarity does not guarantee relevance.
[Measured results](search-example.json).

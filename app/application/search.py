"""Search application logic, separate from HTTP and SQLite."""

from threading import Lock
from typing import Literal

import numpy as np
from pydantic import BaseModel, FiniteFloat

from app.domain.models import Post
from app.retrieval import cosine_similarity, stable_top_k

SearchMode = Literal["semantic", "keyword"]


class SearchHit(BaseModel):
    post: Post
    score: FiniteFloat


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    results: list[SearchHit]


def keyword_scores(query: str, posts: list[Post]) -> np.ndarray:
    """Count distinct words shared by the query and each post."""
    query_words = set(query.lower().split())
    scores = []
    for post in posts:
        post_words = set(post.content.lower().split())
        scores.append(len(query_words & post_words))
    return np.array(scores, dtype=float)


def semantic_scores(query: str, posts: list[Post], encoder) -> np.ndarray:
    """Encode the texts, then compare the query with every post."""
    texts = [post.content for post in posts]
    post_vectors = np.asarray(encoder.encode(texts))
    if post_vectors.ndim != 2 or len(post_vectors) != len(posts):
        raise ValueError("The encoder must return one vector per post.")
    query_vector = encoder.encode([query])[0]
    return cosine_similarity(query_vector, post_vectors)


class SearchService:
    def __init__(self, repository, encoder) -> None:
        self.repository = repository
        self.encoder = encoder
        self._lock = Lock()

    def search(self, query: str, mode: SearchMode = "semantic", limit: int = 5) -> SearchResponse:
        query = query.strip()
        if not query or len(query) > 500 or not 1 <= limit <= 50:
            raise ValueError("Use a nonblank query of at most 500 characters and limit 1–50.")
        if mode not in ("semantic", "keyword"):
            raise ValueError("Choose semantic or keyword search.")

        posts = self.repository.all_posts()
        post_ids = [post.id for post in posts]
        if None in post_ids or len(set(post_ids)) != len(posts):
            raise ValueError("Stored posts must have distinct IDs.")
        if not posts:
            return SearchResponse(query=query, mode=mode, results=[])

        if mode == "keyword":
            scores = keyword_scores(query, posts)
        else:
            # Model calls run one at a time, including its first load.
            with self._lock:
                scores = semantic_scores(query, posts, self.encoder)

        results = []
        for index in stable_top_k(scores, post_ids, limit):
            if mode == "semantic" or scores[index] > 0:
                results.append(SearchHit(post=posts[index], score=float(scores[index])))
        return SearchResponse(query=query, mode=mode, results=results)

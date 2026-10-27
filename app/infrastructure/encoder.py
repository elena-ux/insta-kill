"""Lazy pretrained CPU encoder. The service serializes calls with its lock."""

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class SearchUnavailable(RuntimeError):
    """The semantic encoder could not load or encode; keyword search still works."""


class SentenceEncoder:
    def __init__(self) -> None:
        self.model = None

    def encode(self, texts: list[str]) -> np.ndarray:
        try:
            if self.model is None:
                from sentence_transformers import SentenceTransformer

                self.model = SentenceTransformer(MODEL_NAME, device="cpu")
            return self.model.encode(
                texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
            )
        except Exception as exc:
            raise SearchUnavailable(
                "Search by meaning is unavailable. Try By words or retry later."
            ) from exc

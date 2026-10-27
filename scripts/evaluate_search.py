"""Record a real CPU search run against labeled synthetic examples, not a benchmark claim."""

import argparse
import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from app.application.search import SearchService
from app.db.repository import SQLitePostRepository
from app.infrastructure.encoder import MODEL_NAME, SentenceEncoder
from app.retrieval import cosine_similarity, stable_top_k


def evaluate(database: Path, output: Path) -> dict:
    repo = SQLitePostRepository(database)
    encoder = SentenceEncoder()

    import_start = perf_counter()
    from sentence_transformers import SentenceTransformer

    import_ms = (perf_counter() - import_start) * 1000
    load_start = perf_counter()
    encoder.model = SentenceTransformer(MODEL_NAME, device="cpu")
    model_load_ms = (perf_counter() - load_start) * 1000

    posts = repo.all_posts()
    encoding_start = perf_counter()
    post_vectors = encoder.encode([post.content for post in posts])
    corpus_encoding_ms = (perf_counter() - encoding_start) * 1000

    service = SearchService(repo, encoder)
    labels = json.loads(
        (Path(__file__).resolve().parent.parent / "data/evaluation-queries.json").read_text()
    )
    records = []
    for case in labels:
        for mode in ["keyword", "semantic"]:
            start = perf_counter()
            result = service.search(case["query"], mode, 5)
            elapsed = (perf_counter() - start) * 1000
            ids = [hit.post.id for hit in result.results]
            records.append(
                {
                    **case,
                    "mode": mode,
                    "top_5_ids": ids,
                    "precision_at_5": len(set(ids) & set(case["relevant_ids"])) / 5,
                    "request_ms": elapsed,
                    "results": [h.model_dump(mode="json") for h in result.results],
                }
            )
    query_start = perf_counter()
    query_vector = encoder.encode(["inexpensive supper"])[0]
    query_ms = (perf_counter() - query_start) * 1000
    retrieval_start = perf_counter()
    scores = cosine_similarity(query_vector, post_vectors)
    order = stable_top_k(scores, [p.id for p in posts], 5)
    retrieval_ms = (perf_counter() - retrieval_start) * 1000
    model = encoder.model
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "model": MODEL_NAME,
        "device": str(model.device),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "versions": {
            p: importlib.metadata.version(p)
            for p in ["numpy", "sentence-transformers", "torch", "fastapi"]
        },
        "database": str(database.resolve()),
        "posts": len(posts),
        "embedding_shape": list(post_vectors.shape),
        "embedding_dtype": str(post_vectors.dtype),
        "embedding_bytes": post_vectors.nbytes,
        "model_parameter_bytes": sum(p.numel() * p.element_size() for p in model.parameters()),
        "import_ms": import_ms,
        "model_load_ms": model_load_ms,
        "corpus_encoding_ms": corpus_encoding_ms,
        "warm_query_encoding_ms": query_ms,
        "numpy_retrieval_ms": retrieval_ms,
        "warm_top_5_ids": [posts[i].id for i in order],
        "records": records,
        "interpretation": "Hand-authored synthetic labels; a demonstration of behavior, not held-out model-quality evidence. Precision@5 uses denominator 5 even when fewer results return. Absent-topic cases have no relevant posts.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "records"}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.db, args.output)

"""Measure prediction only, separately from database reads and feature construction."""

import argparse
import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np

from app.infrastructure.like_model import MODEL_PATH, load_model
from app.learned import FEATURES, predict


def benchmark() -> dict:
    saved = load_model()
    rng = np.random.default_rng(0)
    measurements = []
    for count in (1_000, 10_000, 100_000):
        # Synthetic raw signals in [0, 1]; allocation is outside the timed region.
        features = rng.random((count, len(FEATURES)))
        predict(saved, features)  # One warm-up per candidate count.
        times = []
        for _ in range(5):
            started = perf_counter()
            predict(saved, features)
            times.append((perf_counter() - started) * 1000)
        measurements.append({"candidates": count, "runs_ms": times, "median_ms": median(times)})
    return {
        "measured_at_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "model_sha256": hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
        "parameters": sum(saved[key].size for key in ("W1", "b1", "W2", "b2")),
        "model_bytes": MODEL_PATH.stat().st_size,
        "method": "CPU NumPy; seed 0; uniform [0,1] signals; one warm-up and five timed runs per size",
        "includes": "standardization and forward pass only",
        "excludes": "model loading, allocation, database, feature construction and top-k",
        "measurements": measurements,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Also save the measurements as JSON.")
    args = parser.parse_args()
    text = json.dumps(benchmark(), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")

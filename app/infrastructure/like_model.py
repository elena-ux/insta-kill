"""Load the exported notebook model; inference itself lives in app.learned."""

from pathlib import Path
from zipfile import BadZipFile

import numpy as np

from app.learned import FEATURES, Model

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "like_model.npz"
CONSTANTS = ("half_life_days", "popularity_days", "activity_cap", "age_cap_days")


class LearnedUnavailable(RuntimeError):
    pass


def validate_model(saved: Model) -> None:
    """Reject incompatible exports before serving any learned feed requests."""
    required = {"W1", "b1", "W2", "b2", "mu", "sd", "features", *CONSTANTS}
    if not required <= saved.keys():
        raise ValueError("The model is missing required arrays.")
    if saved["features"].tolist() != FEATURES:
        raise ValueError("The model's feature order does not match Week 5.")
    if saved["W1"].ndim != 2 or saved["W1"].shape[1] < 1:
        raise ValueError("The model must have a nonempty hidden layer.")
    hidden = saved["W1"].shape[1]
    shapes = {
        "W1": (6, hidden),
        "b1": (hidden,),
        "W2": (hidden, 1),
        "b2": (1,),
        "mu": (6,),
        "sd": (6,),
    }
    shapes.update({name: () for name in CONSTANTS})
    for name, shape in shapes.items():
        value = saved[name]
        if value.shape != shape or value.dtype.kind not in "fiu" or not np.isfinite(value).all():
            raise ValueError(f"Invalid model array: {name}.")
    if np.any(saved["sd"] <= 0) or any(saved[name] <= 0 for name in CONSTANTS):
        raise ValueError("Standard deviations and signal constants must be positive.")


def load_model(path: Path = MODEL_PATH) -> Model:
    """Load once per application instance; share read-only arrays across requests."""
    try:
        with np.load(path, allow_pickle=False) as archive:
            saved = {name: archive[name] for name in archive.files}
        validate_model(saved)
    except (OSError, ValueError, KeyError, TypeError, EOFError, BadZipFile) as exc:
        raise LearnedUnavailable("The Week 5 model could not be loaded.") from exc
    for value in saved.values():
        value.setflags(write=False)
    return saved

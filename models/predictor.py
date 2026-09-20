"""Load a trained model and produce BUY/SELL/HOLD predictions."""

from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from data.preprocessor import FEATURE_COLUMNS


class Predictor:
    def __init__(self, model_path: str | Path = "models/model.pkl") -> None:
        self.model_path = Path(model_path)
        self.model: Any = joblib.load(self.model_path) if self.model_path.exists() and self.model_path.stat().st_size else None

    def predict(self, features: pd.DataFrame) -> dict[str, float | str]:
        if self.model is None:
            return {"action": "HOLD", "buy": 0.0, "sell": 0.0, "hold": 1.0}

        latest = features[FEATURE_COLUMNS].tail(1)
        probabilities = self.model.predict_proba(latest)[0]
        classes = list(self.model.classes_)
        scores = {str(label).lower(): float(score) for label, score in zip(classes, probabilities)}
        buy_probability = scores.get("buy", 0.0)
        action = "BUY" if buy_probability >= 0.55 else "HOLD"
        return {"action": action, **scores}

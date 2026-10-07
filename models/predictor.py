"""Load a compatible trained model and produce BUY/HOLD predictions."""

from pathlib import Path
import logging
import math
from typing import Any

import joblib
import numpy as np
import pandas as pd

from data.preprocessor import FEATURE_COLUMNS

BASE_DIR = Path(__file__).resolve().parent.parent


class Predictor:
    def __init__(self, model_path: str | Path = "models/model.pkl") -> None:
        self.model_path = Path(model_path)
        if not self.model_path.is_absolute():
            self.model_path = BASE_DIR / self.model_path
        self.model: Any = None
        if self.model_path.exists() and self.model_path.stat().st_size:
            try:
                candidate = joblib.load(self.model_path)
            except Exception:
                logging.exception("Không thể nạp model %s; Predictor sẽ HOLD", self.model_path)
                return

            n_features = getattr(candidate, "n_features_in_", None)
            feature_names = getattr(candidate, "feature_names_in_", None)
            classes = {str(label).lower() for label in getattr(candidate, "classes_", [])}
            if n_features is not None and n_features != len(FEATURE_COLUMNS):
                logging.error(
                    "Model có %s features, cần %s; Predictor sẽ HOLD",
                    n_features, len(FEATURE_COLUMNS),
                )
            elif feature_names is not None and list(feature_names) != FEATURE_COLUMNS:
                logging.error("Thứ tự feature trong model không tương thích; Predictor sẽ HOLD")
            elif not {"buy", "hold"}.issubset(classes):
                logging.error("Model không có đủ class BUY/HOLD; Predictor sẽ HOLD")
            else:
                self.model = candidate

    def predict(self, features: pd.DataFrame) -> dict[str, float | str]:
        if self.model is None:
            return {"action": "HOLD", "buy": 0.0, "hold": 1.0}
        if features.empty:
            return {"action": "HOLD", "buy": 0.0, "hold": 1.0}
        missing = [column for column in FEATURE_COLUMNS if column not in features]
        if missing:
            raise ValueError(f"Thiếu model features: {', '.join(missing)}")

        latest = features.loc[:, FEATURE_COLUMNS].tail(1)
        if not np.isfinite(latest.to_numpy(dtype=float)).all():
            return {"action": "HOLD", "buy": 0.0, "hold": 1.0}
        probabilities = self.model.predict_proba(latest)[0]
        classes = list(self.model.classes_)
        if len(classes) != len(probabilities):
            raise ValueError("Số class của model không khớp số xác suất dự đoán")
        scores = {str(label).lower(): float(score) for label, score in zip(classes, probabilities)}
        buy_probability = scores.get("buy", 0.0)
        if not math.isfinite(buy_probability):
            logging.warning("Model trả xác suất BUY không hữu hạn; dùng HOLD")
            return {"action": "HOLD", "buy": 0.0, "hold": 1.0}
        return {"action": "BUY" if buy_probability >= 0.55 else "HOLD", **scores}

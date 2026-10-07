"""
Module Walk-Forward Retraining cho mô hình Random Forest.
Tự động lấy dữ liệu nến mới, tạo features, gán nhãn và tái huấn luyện định kỳ.
"""

from datetime import datetime
import logging
import os
from pathlib import Path
import joblib
import pandas as pd
import requests
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, f1_score, classification_report
from data.preprocessor import FEATURE_COLUMNS, add_indicators, create_buy_labels

logger = logging.getLogger("CryptoAI")

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "model.pkl"
BACKUP_DIR = MODEL_DIR / "backups"


class MLRetrainer:

    def __init__(self, symbol: str = "BTCUSDT", interval: str = "5m", lookback_candles: int = 3000):
        self.symbol = symbol
        self.interval = interval
        self.lookback_candles = lookback_candles
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    def fetch_recent_klines(self) -> pd.DataFrame:
        """Kéo 3,000 nến 5m gần nhất (~10.4 ngày) từ Binance Public API."""
        all_klines = []
        end_time = None

        batches_needed = (self.lookback_candles // 1000) + 1
        for _ in range(batches_needed):
            url = f"https://api.binance.com/api/v3/klines?symbol={self.symbol}&interval={self.interval}&limit=1000"
            if end_time:
                url += f"&endTime={end_time}"

            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                break
            batch = res.json()
            if not batch:
                break

            all_klines = batch + all_klines
            end_time = batch[0][0] - 1
            if len(all_klines) >= self.lookback_candles:
                break

        df = pd.DataFrame(all_klines, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "num_trades", "taker_base_vol", "taker_quote_vol", "ignore"
        ])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["close_time"] = pd.to_numeric(df["close_time"], errors="coerce")
        df = (
            df.dropna(subset=["open", "high", "low", "close", "volume", "close_time"])
            .drop_duplicates(subset=["open_time"])
            .sort_values("open_time")
            .reset_index(drop=True)
        )
        # Binance includes the currently forming candle in the latest batch.
        if not df.empty:
            df = df.iloc[:-1]
        return df.tail(self.lookback_candles).reset_index(drop=True)

    def generate_features_and_labels(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        """Use the same features and labels as train.py and Predictor."""
        features = add_indicators(df)
        labels = create_buy_labels(
            df,
            horizon=5,
            take_profit_pct=0.015,
            stop_loss_pct=0.01,
        )
        valid_index = features.index.intersection(labels.dropna().index)
        X = features.loc[valid_index, FEATURE_COLUMNS].reset_index(drop=True)
        y = labels.loc[valid_index].reset_index(drop=True)
        return X, y

    def retrain_model(self) -> dict:
        """Thực thi Walk-Forward Retraining."""
        print(f"📥 Đang tải {self.lookback_candles} nến {self.interval} gần nhất từ Binance...")
        df = self.fetch_recent_klines()
        if len(df) < 1000:
            return {"success": False, "reason": "Không đủ dữ liệu nến tải về từ sàn."}

        X, y = self.generate_features_and_labels(df)
        buy_count = int((y == "BUY").sum())
        print(f"📊 Đã tạo đặc trưng cho {len(X)} mẫu nến hợp lệ (Số mẫu BUY: {buy_count} / {len(y)}).")

        label_horizon = 5
        # Chronological split; purge labels whose future horizon crosses the split.
        split_point = int(len(X) * 0.8)
        train_end = split_point - label_horizon
        if train_end <= 0 or split_point >= len(X):
            return {"success": False, "reason": "Không đủ mẫu để chia train/test có purge."}
        X_train, X_test = X.iloc[:train_end], X.iloc[split_point:]
        y_train, y_test = y.iloc[:train_end], y.iloc[split_point:]
        if y_train.nunique() < 2 or y_test.empty:
            return {"success": False, "reason": "Tập train cần cả BUY/HOLD và tập test không được rỗng."}

        # Match train.py so every saved model has the Predictor feature schema.
        model = RandomForestClassifier(
            n_estimators=250,
            max_depth=8,
            min_samples_leaf=15,
            class_weight="balanced",  # Xử lý triệt để bẫy lệch mẫu
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train, y_train)

        # Kiểm định ngoài mẫu (Out-of-Sample Validation)
        y_pred = model.predict(X_test)
        oos_acc = accuracy_score(y_test, y_pred)
        oos_prec = precision_score(y_test, y_pred, pos_label="BUY", zero_division=0)
        oos_f1 = f1_score(y_test, y_pred, pos_label="BUY", zero_division=0)
        report = classification_report(y_test, y_pred, labels=["BUY", "HOLD"], zero_division=0)

        # Trích xuất độ quan trọng của đặc trưng
        importance = dict(zip(X.columns, [round(float(v), 4) for v in model.feature_importances_]))

        # Chốt chặn an toàn: Bắt buộc mô hình phải phát hiện được tín hiệu TĂNG
        if oos_prec < 0.15 and oos_f1 < 0.15:
            return {
                "success": False,
                "reason": f"Mô hình không phân loại được tín hiệu TĂNG (Precision: {oos_prec:.2%}, F1: {oos_f1:.2%})",
                "accuracy": round(oos_acc * 100, 2),
                "precision": round(oos_prec * 100, 2),
            }

        # Write atomically with joblib so Predictor can read it reliably.
        temp_path = MODEL_PATH.with_suffix(".pkl.tmp")
        joblib.dump(model, temp_path)
        if MODEL_PATH.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = BACKUP_DIR / f"model_backup_{ts}.pkl"
            MODEL_PATH.replace(backup_file)
            print(f"📦 Đã sao lưu mô hình cũ ra: {backup_file.name}")
        os.replace(temp_path, MODEL_PATH)

        return {
            "success": True,
            "accuracy": round(oos_acc * 100, 2),
            "precision": round(oos_prec * 100, 2),
            "f1_score": round(oos_f1 * 100, 2),
            "feature_importance": importance,
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "report": report
        }

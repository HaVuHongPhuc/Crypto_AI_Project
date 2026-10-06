"""
Module Walk-Forward Retraining cho mô hình Random Forest.
Tự động lấy dữ liệu nến mới, tạo features, gán nhãn và tái huấn luyện định kỳ.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import pickle
import numpy as np
import pandas as pd
import requests
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, f1_score, classification_report

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
            df[col] = df[col].astype(float)

        return df.tail(self.lookback_candles).reset_index(drop=True)

    def generate_features_and_labels(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        """Tạo đặc trưng kỹ thuật đồng bộ với OperatorAgent và gán nhãn xu hướng."""
        closes = df["close"]

        # 1. Feature Engineering
        df["ema_9"] = closes.ewm(span=9, adjust=False).mean()
        df["ema_21"] = closes.ewm(span=21, adjust=False).mean()
        df["ema_spread"] = (df["ema_9"] - df["ema_21"]) / df["close"] * 100.0

        # RSI 14
        delta = closes.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

        # Khối lượng tương đối
        df["vol_sma"] = df["volume"].rolling(20).mean()
        df["vol_ratio"] = df["volume"] / (df["vol_sma"] + 1e-9)

        # 2. Gán nhãn xu hướng (Biên độ 0.22% trong 3 nến = 15m)
        # 1 (TĂNG): Đủ biên độ lợi nhuận scalping bù phí sàn
        # 0: Sideway hoặc Giảm
        future_return = (closes.shift(-3) - closes) / closes * 100.0
        labels = (future_return > 0.22).astype(int)

        feature_cols = ["ema_spread", "rsi_14", "vol_ratio"]
        clean_df = df[feature_cols].copy()
        valid_idx = clean_df.dropna().index.intersection(labels.dropna().index)

        return clean_df.loc[valid_idx], labels.loc[valid_idx]

    def retrain_model(self) -> dict:
        """Thực thi Walk-Forward Retraining."""
        print(f"📥 Đang tải {self.lookback_candles} nến {self.interval} gần nhất từ Binance...")
        df = self.fetch_recent_klines()
        if len(df) < 1000:
            return {"success": False, "reason": "Không đủ dữ liệu nến tải về từ sàn."}

        X, y = self.generate_features_and_labels(df)
        print(f"📊 Đã tạo đặc trưng cho {len(X)} mẫu nến hợp lệ (Số mẫu TĂNG: {int(y.sum())} / {len(y)}).")

        # Phân chia Walk-Forward theo trục thời gian (80% Train, 20% Out-of-Sample)
        split_point = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_point], X.iloc[split_point:]
        y_train, y_test = y.iloc[:split_point], y.iloc[split_point:]

        # Huấn luyện Random Forest cân bằng trọng số
        model = RandomForestClassifier(
            n_estimators=150,
            max_depth=6,
            min_samples_split=15,
            class_weight="balanced",  # Xử lý triệt để bẫy lệch mẫu
            random_state=42
        )
        model.fit(X_train, y_train)

        # Kiểm định ngoài mẫu (Out-of-Sample Validation)
        y_pred = model.predict(X_test)
        oos_acc = accuracy_score(y_test, y_pred)
        oos_prec = precision_score(y_test, y_pred, zero_division=0)
        oos_f1 = f1_score(y_test, y_pred, zero_division=0)
        report = classification_report(y_test, y_pred, zero_division=0)

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

        # Sao lưu mô hình cũ
        if MODEL_PATH.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = BACKUP_DIR / f"model_backup_{ts}.pkl"
            MODEL_PATH.rename(backup_file)
            print(f"📦 Đã sao lưu mô hình cũ ra: {backup_file.name}")

        # Lưu mô hình mới
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)

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
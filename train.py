"""Train the BUY/HOLD model from the configured 5-minute history dataset."""

import os

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

from data.preprocessor import FEATURE_COLUMNS, add_indicators, create_buy_labels


def create_labels(
    df: pd.DataFrame,
    future_candles: int = 5,
    threshold: float = 0.015,
    stop_loss_pct: float = 0.01,
) -> pd.DataFrame:
    """Label BUY only when take-profit is hit before the stop in the horizon.

    If TP and SL both occur in one OHLC candle, the shared labeler conservatively
    treats the stop as first. The final horizon candles are excluded.
    """
    df = df.copy()
    df["label"] = create_buy_labels(
        df,
        horizon=future_candles,
        take_profit_pct=threshold,
        stop_loss_pct=stop_loss_pct,
    )
    return df.dropna(subset=["label"]).reset_index(drop=True)


def main():
    dataset_path = "storage/btc_5m.csv"

    if not os.path.exists(dataset_path):
        print(f"Không tìm thấy file {dataset_path}!")
        print("Hãy chạy script: py fetch_and_save_dataset.py trước để tải dữ liệu.")
        return

    print("=" * 65)
    print(f"Đang đọc dữ liệu từ {dataset_path}...")
    df_raw = pd.read_csv(dataset_path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(df_raw.columns))
    if missing:
        raise ValueError(f"Dataset thiếu cột OHLCV/timestamp: {', '.join(missing)}")
    df_raw["timestamp"] = pd.to_numeric(df_raw["timestamp"], errors="coerce")
    df_raw = (
        df_raw.dropna(subset=["timestamp"])
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    if df_raw.empty:
        raise ValueError("Dataset không có nến hợp lệ")
    print(f"Tổng số nến đọc được: {len(df_raw):,} cây nến.")

    print("Đang trích xuất chỉ báo kỹ thuật...")
    df_features = add_indicators(df_raw)

    print("Đang gán nhãn BUY/HOLD theo sóng giá...")
    label_horizon = 5
    df_labeled = create_labels(df_features, future_candles=label_horizon, threshold=0.015, stop_loss_pct=0.01)

    feature_cols = FEATURE_COLUMNS

    X = df_labeled[feature_cols]
    y = df_labeled["label"]

    # Chia tập Train/Test theo dòng thời gian (80% học, 20% kiểm tra), KHÔNG shuffle
    split_idx = int(len(df_labeled) * 0.8)
    # Purge the final label horizon from training so its future candles cannot
    # overlap the first test candles.
    train_end = split_idx - label_horizon
    if train_end <= 0 or split_idx >= len(df_labeled):
        raise ValueError("Dataset quá nhỏ để chia train/test theo thời gian an toàn")
    X_train, X_test = X.iloc[:train_end], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:train_end], y.iloc[split_idx:]

    print("-" * 65)
    print("PHÂN BỔ TẬP DỮ LIỆU:")
    print(f"Số mẫu Train : {len(X_train):,} nến")
    print(y_train.value_counts().to_string())
    print(f"\nSố mẫu Test  : {len(X_test):,} nến")
    print(y_test.value_counts().to_string())
    print("-" * 65)

    print("Đang huấn luyện mô hình Random Forest...")
    model = RandomForestClassifier(
        n_estimators=250,
        max_depth=8,
        min_samples_leaf=15,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    if y_train.nunique() < 2:
        raise ValueError("Tập train cần có cả nhãn BUY và HOLD")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    print("\n--- MA TRẬN NHẦM LẪN (CONFUSION MATRIX) ---")
    cm = confusion_matrix(y_test, y_pred, labels=["BUY", "HOLD"])
    cm_df = pd.DataFrame(cm, index=["Thực tế BUY", "Thực tế HOLD"], columns=["Đoán BUY", "Đoán HOLD"])
    print(cm_df)

    print("\n--- BÁO CÁO HIỆU NĂNG (CLASSIFICATION REPORT) ---")
    print(classification_report(y_test, y_pred, digits=3, zero_division=0))

    print("--- ĐỘ QUAN TRỌNG CỦA CÁC CHỈ BÁO ---")
    importances = pd.Series(model.feature_importances_, index=feature_cols).sort_values(ascending=False)
    for col, val in importances.items():
        print(f"{col:<18}: {val:.4f}")

    os.makedirs("models", exist_ok=True)
    joblib.dump(model, "models/model.pkl")
    print("-" * 65)
    print("Đã cập nhật mô hình mới vào models/model.pkl thành công!")
    print("=" * 65)


if __name__ == "__main__":
    main()

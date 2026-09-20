"""Huấn luyện mô hình Random Forest từ tập dữ liệu lịch sử btc_15m.csv."""

import os

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

from data.preprocessor import add_indicators


def create_labels(df: pd.DataFrame, future_candles: int = 4, threshold: float = 0.0035) -> pd.DataFrame:
    """
    Gán nhãn theo triển vọng lợi nhuận thực tế:
    - Quét 4 cây nến tiếp theo (tương đương 20 phút trong khung 5m).
    - Nếu mức giá cao nhất đạt mức tăng >= 0.35% (đủ bù trừ phí sàn và có lãi trên sóng ngắn) -> BUY.
    - Ngược lại -> HOLD.
    """
    df = df.copy()

    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=future_candles)
    future_high = df["high"].shift(-1).rolling(window=indexer).max()

    df["future_return"] = (future_high - df["close"]) / df["close"]
    df["label"] = df["future_return"].apply(lambda r: "BUY" if r >= threshold else "HOLD")

    return df.dropna(subset=["future_return"]).reset_index(drop=True)


def main():
    dataset_path = "storage/btc_5m.csv"

    if not os.path.exists(dataset_path):
        print(f"Không tìm thấy file {dataset_path}!")
        print("Hãy chạy script: py fetch_and_save_dataset.py trước để tải dữ liệu.")
        return

    print("=" * 65)
    print(f"Đang đọc dữ liệu từ {dataset_path}...")
    df_raw = pd.read_csv(dataset_path)
    print(f"Tổng số nến đọc được: {len(df_raw):,} cây nến.")

    print("Đang trích xuất chỉ báo kỹ thuật...")
    df_features = add_indicators(df_raw)

    print("Đang gán nhãn BUY/HOLD theo sóng giá...")
    df_labeled = create_labels(df_features, future_candles=4, threshold=0.0035)

    feature_cols = [
        "rsi_14",
        "macd",
        "macd_signal",
        "ema_9",
        "ema_21",
        "ema_spread_pct",
        "volume_change",
    ]

    X = df_labeled[feature_cols]
    y = df_labeled["label"]

    # Chia tập Train/Test theo dòng thời gian (80% học, 20% kiểm tra), KHÔNG shuffle
    split_idx = int(len(df_labeled) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

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

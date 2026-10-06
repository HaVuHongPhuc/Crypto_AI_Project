"""Script chạy thử nghiệm Walk-Forward Retraining ngay lập tức."""

import pickle
from pathlib import Path
from engine.ml_retrainer import MLRetrainer

print("=" * 70)
print("🤖 BẮT ĐẦU CHẠY THỬ NGHIỆM TÁI HUẤN LUYỆN MODEL (WALK-FORWARD)")
print("=" * 70)

# Khởi tạo bộ huấn luyện cho BTC/USDT 5m với 3,000 nến
retrainer = MLRetrainer(symbol="BTCUSDT", interval="5m", lookback_candles=3000)

result = retrainer.retrain_model()

print("\n" + "=" * 70)
if result.get("success"):
    print("✅ [KẾT QUẢ]: TÁI HUẤN LUYỆN VÀ LƯU MÔ HÌNH THÀNH CÔNG!")
    print(f"📈 Độ chính xác Out-of-Sample (OOS Accuracy) : {result['accuracy']}%")
    print(f"🎯 Độ chuẩn xác tín hiệu (OOS Precision)     : {result['precision']}%")
    print(f"📚 Số mẫu huấn luyện (Train)                : {result['train_samples']} nến")
    print(f"🧪 Số mẫu kiểm tra độc lập (OOS Test)        : {result['test_samples']} nến")
    
    print("\n🔍 Mức độ đóng góp của từng chỉ báo (Feature Importance):")
    for feat, score in result["feature_importance"].items():
        print(f"   • {feat:<15}: {score:.2%}")

    print("\n📋 Chi tiết bảng đánh giá phân loại:")
    print(result["report"])

    # Kiểm tra nạp thử nghiệm mô hình vừa lưu
    model_path = Path("models/model.pkl")
    if model_path.exists():
        with open(model_path, "rb") as f:
            loaded_model = pickle.load(f)
        # Thử dự đoán với 1 mẫu giả lập
        dummy_features = [[0.05, 58.2, 1.25]]  # [ema_spread, rsi_14, vol_ratio]
        prob = loaded_model.predict_proba(dummy_features)[0][1]
        print(f"⚡ Kiểm tra nạp mô hình: OK | Xác suất tăng giá cho mẫu thử: {prob:.2%}")
else:
    print("❌ [THẤT BẠI]:", result.get("reason"))

print("=" * 70)
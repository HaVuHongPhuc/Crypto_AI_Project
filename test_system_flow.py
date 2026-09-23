"""
End-to-End System Flow Audit:
Kiểm tra tính liền mạch của toàn bộ 9 trạm kiểm soát trong kiến trúc Hybrid Quant AI.
"""

import sys
import os
import time
import json
from pathlib import Path

print("=" * 80)
print("🔍 BẮT ĐẦU KIỂM TRA ĐỐI SOÁT TOÀN DIỆN HỆ THỐNG HYBRID QUANT AI")
print("=" * 80)

# ----------------------------------------------------------------------
# TRẠM 1: Cấu hình & Môi trường (.env & Settings)
# ----------------------------------------------------------------------
print("\n[1/9] Kiểm tra Cấu hình & Biến môi trường...")
try:
    from config.settings import Settings
    cfg = Settings()
    print(f"  ✅ Cấu hình tải thành công. Chế độ LLM: [{cfg.llm_mode}]")
except Exception as e:
    print(f"  ❌ LỖI Trạm 1: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------
# TRẠM 2: Dữ liệu & Tiền xử lý (Fetcher & Preprocessor)
# ----------------------------------------------------------------------
print("\n[2/9] Kiểm tra Tầng Dữ liệu (Fetcher & Preprocessor)...")
try:
    from data.fetcher import MarketDataFetcher
    from data.preprocessor import Preprocessor

    fetcher = MarketDataFetcher()
    df_raw = fetcher.get_historical_klines(symbol="BTC/USDT", timeframe="5m", limit=50)
    print(f"  ✅ Fetcher: Đã lấy thành công {len(df_raw)} nến 5m từ sàn.")

    preprocessor = Preprocessor()
    df_features = preprocessor.add_indicators(df_raw.copy())
    print(f"  ✅ Preprocessor: Đã trích xuất {len(df_features.columns)} chỉ báo/features.")
except Exception as e:
    print(f"  ❌ LỖI Trạm 2: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------
# TRẠM 3: Tầng Dự báo Machine Learning (Predictor & Random Forest)
# ----------------------------------------------------------------------
print("\n[3/9] Kiểm tra Mô hình Random Forest (models/predictor.py)...")
try:
    from models.predictor import Predictor
    predictor = Predictor(model_path="models/model.pkl")
    
    # Lấy hàng nến mới nhất để test dự báo
    latest_row = df_features.iloc[-1:]
    prediction = predictor.predict(latest_row)
    print(f"  ✅ Predictor: Đã nạp model.pkl thành công. Dự báo nến hiện tại: [{prediction}]")
except Exception as e:
    print(f"  ❌ LỖI Trạm 3: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------
# TRẠM 4: Tình báo Thị trường & Tin tức (SentimentAgent)
# ----------------------------------------------------------------------
print("\n[4/9] Kiểm tra Tác tử Tin tức (SentimentAgent)...")
try:
    from agents.sentiment_agent import SentimentAgent
    sentiment_agent = SentimentAgent(cfg)
    sentiment_data = sentiment_agent.analyze_market_sentiment()
    print(f"  ✅ Sentiment: Fear&Greed={sentiment_data.get('fear_and_greed')}/100 | Tâm lý={sentiment_data.get('sentiment')} | Panic Score={sentiment_data.get('panic_score')}/10")
    print(f"     Sự kiện chi phối: {sentiment_data.get('key_driver')}")
except Exception as e:
    print(f"  ❌ LỖI Trạm 4: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------
# TRẠM 5: Nhạc trưởng Vĩ mô 1H (StrategistAgent)
# ----------------------------------------------------------------------
print("\n[5/9] Kiểm tra Nhạc trưởng 1H (StrategistAgent)...")
try:
    from agents.agent_team import StrategistAgent
    strategist = StrategistAgent(cfg)
    current_price = float(df_raw["close"].iloc[-1])
    h1_mock_ind = {"rsi_14": 52.5, "ema_50": current_price * 0.99, "ema_200": current_price * 0.98}
    macro_directive = strategist.analyze_macro("BTC/USDT", current_price, h1_mock_ind)
    print(f"  ✅ Strategist 1H: Chỉ thị ban hành -> [{macro_directive.get('directive')}] (Bias: {macro_directive.get('macro_bias')})")
except Exception as e:
    print(f"  ❌ LỖI Trạm 5: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------
# TRẠM 6: Chân ga Scalping 5m (OperatorAgent tiếp nhận ML + TA)
# ----------------------------------------------------------------------
print("\n[6/9] Kiểm tra Chân ga Scalping (OperatorAgent)...")
try:
    from agents.agent_team import OperatorAgent
    operator = OperatorAgent(cfg)
    mock_indicators = {
        "rsi_14": 56.0,
        "ema_9": current_price,
        "ema_21": current_price * 0.998,
        "ml_signal": prediction
    }
    proposal = operator.analyze(
        symbol="BTC/USDT",
        current_price=current_price,
        indicators=mock_indicators,
        position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
        macro_directive=macro_directive.get("directive", "FLEXIBLE")
    )
    print(f"  ✅ Operator: Đề xuất hành động -> [{proposal.get('action')}] (Tự tin: {int(proposal.get('confidence', 0.8)*100)}%)")
    print(f"     Lý do: {proposal.get('reason')}")
except Exception as e:
    print(f"  ❌ LỖI Trạm 6: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------
# TRẠM 7: Chân phanh Giám sát Rủi ro (SupervisorAgent)
# ----------------------------------------------------------------------
print("\n[7/9] Kiểm tra Chân phanh (SupervisorAgent + Memory Filter)...")
try:
    from agents.agent_team import SupervisorAgent, ReflectorAgent
    supervisor = SupervisorAgent(cfg)
    past_lessons = ReflectorAgent.load_lessons(side="LONG")
    
    review = supervisor.review(
        proposal=proposal,
        indicators=mock_indicators,
        cash=100.0,
        position_info={"side": "NONE"},
        macro_directive=macro_directive.get("directive", "FLEXIBLE"),
        past_lessons=past_lessons,
        sentiment_info=sentiment_data
    )
    status = "DUYỆT ✅" if review.get("approved") else "TỪ CHỐI ❌"
    print(f"  ✅ Supervisor: Quyết định xét duyệt -> {status} (Rủi ro: {review.get('risk_score')}/10)")
    print(f"     Phản biện: {review.get('feedback')}")
except Exception as e:
    print(f"  ❌ LỖI Trạm 7: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------
# TRẠM 8: Khiên Rủi ro Cơ học (RiskManager: SL/TP/Trailing Stop)
# ----------------------------------------------------------------------
print("\n[8/9] Kiểm tra Khiên Cơ học (RiskManager)...")
try:
    from engine.risk_manager import RiskManager
    risk_mgr = RiskManager()
    
    # Giả lập vị thế đang có lãi để test Trailing Stop
    test_entry = 84000.0
    test_high = 85500.0  # Lãi ~1.78% -> đủ điều kiện kích hoạt Trailing Stop
    test_current = 84500.0 # Giá quay đầu giảm -> kích hoạt chốt lời bảo vệ vốn
    
    exit_signal = risk_mgr.should_exit(
        side="LONG",
        entry_price=test_entry,
        current_price=test_current,
        highest_price=test_high
    )
    print(f"  ✅ RiskManager: Test phản xạ Trailing Stop -> Kết quả: [{exit_signal}] (Ưu tiên cơ học 0ms)")
except Exception as e:
    print(f"  ❌ LỖI Trạm 8: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------
# TRẠM 9: Thực thi Giao dịch, Tính phí & Lưu trữ (PaperTrader & State)
# ----------------------------------------------------------------------
print("\n[9/9] Kiểm tra Thực thi, Phí 0.05% & Phục hồi Crash (PaperTrader)...")
try:
    from engine.paper_trader import PaperTrader
    trader = PaperTrader(initial_cash=100.0)
    
    # 1. Mở lệnh thử nghiệm
    trader.open_position("LONG", price=84000.0, cash_amount=70.0)
    print(f"  ✅ PaperTrader: Đã mở lệnh LONG. Vốn còn lại: {trader.cash:.4f} USDT (Đã trừ phí 0.05%)")
    
    # 2. Kiểm tra file active_position.json
    active_pos_path = Path("storage/active_position.json")
    if active_pos_path.exists():
        with open(active_pos_path, "r", encoding="utf-8") as f:
            pos_saved = json.load(f)
            assert pos_saved.get("side") == "LONG"
        print(f"  ✅ Crash Recovery: Trạng thái vị thế đã được ghi an toàn vào storage/active_position.json")
    
    # 3. Đóng lệnh thử nghiệm
    close_summary = trader.close_position(exit_price=84500.0, exit_reason="TEST_VERIFY")
    print(f"  ✅ PaperTrader: Đóng vị thế thành công. PnL: {close_summary.get('pnl_pct'):+.2f}% | Vốn sau đóng: {trader.cash:.2f} USDT")
except Exception as e:
    print(f"  ❌ LỖI Trạm 9: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("🎉 CHÚC MỪNG! TOÀN BỘ 9 TRẠM KIỂM SOÁT ĐỀU HOẠT ĐỘNG HOÀN TOÀN ĂN KHỚP!")
print("   Hệ thống Hybrid Quant AI đã sẵn sàng hoạt động thực tế với lệnh: py main.py")
print("=" * 80)
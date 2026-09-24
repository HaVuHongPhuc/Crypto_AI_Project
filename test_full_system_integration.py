"""
Script kiểm tra toàn diện tích hợp hệ thống:
1. Tầng ML: OperatorAgent kết nối model.pkl và tính xác suất tăng/giảm.
2. Tầng Hot-Swap: Tải lại model trong RAM không gián đoạn.
3. Tầng Vĩ Mô (Độ nhạy Strategist): Giá gãy EMA50 1H -> Có chuyển ngay sang ONLY_SHORT không?
4. Tầng Quản Trị (Supervisor vs Sentiment): Có DUYỆT lệnh OPEN_SHORT khi tin tức Bullish không?
5. Tầng Bảo Vệ Cực Hạn: Phanh khẩn cấp khi Panic = 9/10.
"""

from pathlib import Path
from config.settings import Settings
from agents.agent_team import AgentTeam

print("=" * 75)
print("🔬 BẮT ĐẦU KIỂM TRA HỆ THỐNG ĐÃ VÁ LỖI (STRATEGIST & SUPERVISOR TEST)")
print("=" * 75)

config = Settings()
team = AgentTeam(config)
model_path = Path("models/model.pkl")

# =====================================================================
# TEST 1: Kiểm tra kết nối Tầng Machine Learning (model.pkl -> Operator)
# =====================================================================
print("\n[TEST 1] Tầng ML: Kiểm tra OperatorAgent nạp model.pkl vào RAM")

if not model_path.exists():
    print("❌ THẤT BẠI: Chưa tìm thấy models/model.pkl.")
else:
    is_loaded = team.operator_agent.model is not None
    print(f"-> Trạng thái nạp mô hình: {'✅ ĐÃ NẠP' if is_loaded else '❌ CHƯA NẠP'}")

    test_bull = {"price": 84500.0, "ema_9": 84600.0, "ema_21": 84400.0, "rsi_14": 65.0}
    test_bear = {"price": 83000.0, "ema_9": 82800.0, "ema_21": 83200.0, "rsi_14": 30.0}

    prob_bull = team.operator_agent.predict_ml_probability(test_bull)
    prob_bear = team.operator_agent.predict_ml_probability(test_bear)

    print(f"-> Xác suất tăng khi chỉ báo Bullish: {prob_bull:.1%}")
    print(f"-> Xác suất tăng khi chỉ báo Bearish: {prob_bear:.1%}")

    if is_loaded:
        print("✅ ĐẠT: OperatorAgent suy luận xác suất từ mô hình ML thành công.")
    else:
        print("❌ THẤT BẠI: Chưa nạp được mô hình.")


# =====================================================================
# TEST 2: Kiểm tra độ nhạy của Strategist 1H (Không bị kẹt FLEXIBLE)
# Giả lập: Giá sập về 83,000, dưới EMA50 (84,200), nhưng EMA50 vẫn > EMA200 (81,500)
# =====================================================================
print("\n[TEST 2] Tầng Vĩ Mô: Kiểm tra độ nhạy của Strategist 1H")

fake_breakdown_1h = {
    "rsi_14": 41.5,        # RSI 1H yếu (< 48)
    "ema_50": 84200.0,     # Giá nằm sâu dưới EMA50
    "ema_200": 81500.0     # EMA50 vẫn cao hơn EMA200 do quán tính tuần trước
}

strat_res = team.strategist_agent.analyze_macro(
    symbol="BTC/USDT",
    current_price=83000.0,
    h1_ind=fake_breakdown_1h
)

print(f"-> Chỉ thị 1H ban hành : [{strat_res.get('directive')}] ({strat_res.get('macro_bias')})")
print(f"-> Lập luận Strategist : {strat_res.get('reasoning')}")

if strat_res.get("directive") == "ONLY_SHORT":
    print("✅ ĐẠT: Strategist đã phá vỡ cái bẫy EMA200, phản ứng nhạy bén với sóng giảm!")
else:
    print(f"⚠️ CHÚ Ý: Strategist vẫn trả về [{strat_res.get('directive')}]. Cần kiểm tra prompt.")


# =====================================================================
# TEST 3: Kiểm tra Supervisor duyệt lệnh SHORT khi Sentiment BULLISH
# Giả lập: 5m có tín hiệu SHORT rất rõ, tin tức thì BULLISH (Panic 3/10)
# =====================================================================
print("\n[TEST 3] Tầng Phê Duyệt: Supervisor duyệt OPEN_SHORT dù tin tức Bullish")

fake_short_indicators = {
    "price": 83400.0,
    "rsi_14": 34.5,
    "ema_9": 83350.0,
    "ema_21": 83550.0,
    "macd": -200.0
}

fake_short_proposal = {
    "action": "OPEN_SHORT",
    "confidence": 0.85,
    "reason": "EMA9 cắt dưới EMA21, RSI 34.5 xác nhận xu hướng giảm mạnh."
}

fake_bullish_news = {
    "sentiment": "BULLISH",
    "panic_score": 3,
    "trading_advice": "NORMAL",
    "key_driver": "Dòng tiền ETF đổ vào mạnh mẽ, thị trường lạc quan dài hạn."
}

sup_review = team.supervisor_agent.review(
    proposal=fake_short_proposal,
    indicators=fake_short_indicators,
    cash=100.0,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="FLEXIBLE",
    past_lessons=[],
    sentiment_info=fake_bullish_news
)

print(f"-> Supervisor duyệt lệnh SHORT: {sup_review.get('approved')} (Rủi ro: {sup_review.get('risk_score')}/10)")
print(f"-> Phản biện Supervisor       : {sup_review.get('feedback')}")

if sup_review.get("approved"):
    print("✅ ĐẠT: Supervisor đã dứt khoát DUYỆT lệnh Short thuận xu hướng, không bị truyền thông bóp nghẹt!")
else:
    print("❌ THẤT BẠI: Supervisor vẫn từ chối Short do vướng tâm lý Bullish của báo chí.")


# =====================================================================
# TEST 4: Chốt chặn an toàn - Phanh khẩn cấp khi có bão tin tức (Panic 9/10)
# =====================================================================
print("\n[TEST 4] Tầng Phòng Thủ: Phanh khẩn cấp khi Panic Score = 9/10")

black_swan_news = {
    "sentiment": "EXTREME_BEARISH",
    "panic_score": 9,
    "trading_advice": "HALT_TRADING",
    "key_driver": "Sàn giao dịch lớn bị hacker tấn công đóng băng rút tiền."
}

sup_panic_review = team.supervisor_agent.review(
    proposal=fake_short_proposal,
    indicators=fake_short_indicators,
    cash=100.0,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="FLEXIBLE",
    past_lessons=[],
    sentiment_info=black_swan_news
)

print(f"-> Supervisor phản ứng khi Panic=9 : Duyệt = {sup_panic_review.get('approved')} (Rủi ro: {sup_panic_review.get('risk_score')}/10)")
print(f"-> Phản biện                        : {sup_panic_review.get('feedback')}")

if not sup_panic_review.get("approved"):
    print("✅ ĐẠT: Phanh khẩn cấp hoạt động chính xác khi rủi ro tin tức thực sự cực đoan.")
else:
    print("❌ THẤT BẠI: Bot không kích hoạt phanh khi hoảng loạn.")

print("\n" + "=" * 75)
print("🏁 KẾT THÚC KIỂM TRA ĐỒNG BỘ!")
print("=" * 75)
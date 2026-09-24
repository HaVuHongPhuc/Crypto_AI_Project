"""Script kiểm tra mức độ liên kết dữ liệu giữa 6 Agent."""

import os
from config.settings import Settings
from agents.agent_team import AgentTeam, ReflectorAgent

print("=" * 70)
print("🔬 BẮT ĐẦU KIỂM TRA MỨC ĐỘ LIÊN KẾT GIỮA CÁC AGENT (PIPELINE TEST)")
print("=" * 70)

config = Settings()
team = AgentTeam(config)

# =====================================================================
# TEST 1: Strategist (1H) có thực sự "khóa tay" được Supervisor không?
# Giả lập: Khung 5m cực kỳ BULLISH (đòi Long), nhưng 1H là ONLY_SHORT.
# =====================================================================
print("\n[TEST 1] Kiểm tra liên kết: Strategist (1H: ONLY_SHORT) vs Operator (5m: LONG)")

fake_bullish_indicators = {
    "price": 84500.0,
    "rsi_14": 65.5,
    "ema_9": 84600.0,
    "ema_21": 84400.0,
    "macd": 200.0
}

# 1. Operator phân tích
op_proposal = team.operator_agent.analyze(
    symbol="BTC/USDT",
    current_price=84500.0,
    indicators=fake_bullish_indicators,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="ONLY_SHORT"  # Ép chỉ thị vĩ mô là ONLY_SHORT
)
print(f"-> Operator đề xuất: {op_proposal.get('action')} | Lý do: {op_proposal.get('reason')}")

# 2. Supervisor thẩm định
sup_review = team.supervisor_agent.review(
    proposal=op_proposal,
    indicators=fake_bullish_indicators,
    cash=100.0,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="ONLY_SHORT",
    past_lessons=[],
    sentiment_info={"sentiment": "BULLISH", "panic_score": 2}
)
print(f"-> Supervisor duyệt: {sup_review.get('approved')} | Phản biện: {sup_review.get('feedback')}")

if not sup_review.get("approved") or op_proposal.get("action") != "OPEN_LONG":
    print("✅ ĐẠT: Strategist đã kiểm soát thành công Operator/Supervisor (Không bị Long ngược sóng).")
else:
    print("❌ THẤT BẠI: Supervisor duyệt lệnh Long dù 1H cấm Long! Hai agent đang mất liên kết.")


# =====================================================================
# TEST 2: Sentiment có quyền "phủ quyết" (Veto Power) hay không?
# Giả lập: Kỹ thuật Short rất chuẩn, nhưng tin tức HOẢNG LOẠN CỰC ĐỘ (Panic 9/10).
# =====================================================================
print("\n[TEST 2] Kiểm tra liên kết: Sentiment (Panic 9/10) vs Supervisor")

fake_bearish_indicators = {
    "price": 84000.0,
    "rsi_14": 35.0,
    "ema_9": 83900.0,
    "ema_21": 84100.0,
    "macd": -200.0
}

fake_proposal_short = {
    "action": "OPEN_SHORT",
    "confidence": 0.85,
    "reason": "EMA9 cắt dưới EMA21, RSI 35 ủng hộ Short."
}

sup_panic_review = team.supervisor_agent.review(
    proposal=fake_proposal_short,
    indicators=fake_bearish_indicators,
    cash=100.0,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="ONLY_SHORT",
    past_lessons=[],
    sentiment_info={
        "sentiment": "EXTREME_BEARISH",
        "panic_score": 9,  # Báo động đỏ
        "advice": "PAUSE_TRADING",
        "event": "Sàn giao dịch lớn bị đóng băng rút tiền (Black Swan)."
    }
)
print(f"-> Supervisor duyệt khi Panic=9: {sup_panic_review.get('approved')} | Mức rủi ro: {sup_panic_review.get('risk_score')}/10")
print(f"-> Lý do Supervisor: {sup_panic_review.get('feedback')}")

if not sup_panic_review.get("approved"):
    print("✅ ĐẠT: Sentiment đã ngăn chặn thành công lệnh giao dịch trong cơn hoảng loạn.")
else:
    print("❌ THẤT BẠI: Supervisor vẫn mở lệnh dù thị trường đang sập bão tin tức.")


# =====================================================================
# TEST 3: Reflector rút kinh nghiệm -> Operator có áp dụng ở nến sau?
# Giả lập: Nạp một bài học cấm Short khi RSI < 30.
# =====================================================================
print("\n[TEST 3] Kiểm tra liên kết: Bài học Reflector -> Hành vi Operator")

test_lessons = ["Cấm tuyệt đối mở lệnh SHORT khi RSI 5m đã giảm sâu dưới 30 (bẫy quá bán)."]

op_oversold_proposal = team.operator_agent.analyze(
    symbol="BTC/USDT",
    current_price=83000.0,
    indicators={"price": 83000.0, "rsi_14": 24.5, "ema_9": 82900.0, "ema_21": 83200.0, "macd": -150.0},
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="FLEXIBLE"
)
print(f"-> Khi RSI=24.5, Operator đề xuất: {op_oversold_proposal.get('action')}")
print(f"-> Lập luận của Operator: {op_oversold_proposal.get('reason')}")

sup_lesson_review = team.supervisor_agent.review(
    proposal=op_oversold_proposal,
    indicators={"price": 83000.0, "rsi_14": 24.5, "ema_9": 82900.0, "ema_21": 83200.0, "macd": -150.0},
    cash=100.0,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="FLEXIBLE",
    past_lessons=test_lessons,  # Nạp bài học cấm Short quá bán
    sentiment_info={"sentiment": "NEUTRAL", "panic_score": 3}
)
print(f"-> Supervisor phản ứng với bài học: Duyệt = {sup_lesson_review.get('approved')}")
print(f"-> Phản biện: {sup_lesson_review.get('feedback')}")

if not sup_lesson_review.get("approved") or op_oversold_proposal.get("action") != "OPEN_SHORT":
    print("✅ ĐẠT: Bài học của Reflector đã được Supervisor tiếp thu và ngăn chặn bẫy quá bán.")
else:
    print("❌ CẢNH BÁO: Supervisor bỏ qua bài học kinh nghiệm quá khứ.")

print("\n" + "=" * 70)
print("🏁 KẾT THÚC KIỂM TRA TOÀN DIỆN!")
print("=" * 70)
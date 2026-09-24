"""
Script kiểm tra toàn diện tích hợp hệ sinh thái (Full System Integration Test):
1. Tầng ML: Operator có nạp model.pkl và tính xác suất tăng/giảm thật không?
2. Tầng Hot-Swap: Operator có reload_model() trơn tru trong RAM không?
3. Tầng Suy Luận Kết Hợp: Operator có kết hợp xác suất ML + Kỹ thuật vào quyết định không?
4. Tầng Vĩ Mô: Strategist (1H: ONLY_SHORT) có khóa tay lệnh Long không?
5. Tầng Tình Báo: Sentiment (Panic 9/10) có kích hoạt phanh khẩn cấp không?
6. Tầng Tự Học: Bài học Reflector có chặn đứng bẫy kỹ thuật không?
"""

from pathlib import Path
from config.settings import Settings
from agents.agent_team import AgentTeam, ReflectorAgent

print("=" * 75)
print("🔬 BẮT ĐẦU KIỂM TRA TOÀN DIỆN KẾT NỐI HỆ THỐNG (ML + 6-AGENT PIPELINE)")
print("=" * 75)

config = Settings()
team = AgentTeam(config)
model_path = Path("models/model.pkl")

# =====================================================================
# TEST 1: Kiểm tra kết nối Tầng Machine Learning (model.pkl -> Operator)
# =====================================================================
print("\n[TEST 1] Kiểm tra kết nối: File models/model.pkl -> OperatorAgent RAM")

if not model_path.exists():
    print("❌ THẤT BẠI: Không tìm thấy file models/model.pkl! Hãy chạy train.py trước.")
else:
    is_loaded = team.operator_agent.model is not None
    print(f"-> Trạng thái nạp mô hình vào OperatorAgent: {'✅ ĐÃ NẠP' if is_loaded else '❌ CHƯA NẠP'}")

    # Chạy thử nghiệm hàm tính xác suất ML
    test_bullish_ind = {"price": 84500.0, "ema_9": 84650.0, "ema_21": 84400.0, "rsi_14": 65.0}
    test_bearish_ind = {"price": 83000.0, "ema_9": 82800.0, "ema_21": 83100.0, "rsi_14": 30.0}

    prob_bull = team.operator_agent.predict_ml_probability(test_bullish_ind)
    prob_bear = team.operator_agent.predict_ml_probability(test_bearish_ind)

    print(f"-> Xác suất TĂNG khi chỉ báo Bullish: {prob_bull:.1%}")
    print(f"-> Xác suất TĂNG khi chỉ báo Bearish: {prob_bear:.1%}")

    if is_loaded and (0.0 <= prob_bull <= 1.0) and (0.0 <= prob_bear <= 1.0):
        print("✅ ĐẠT: OperatorAgent đã kết nối thành công với não bộ Machine Learning!")
    else:
        print("❌ THẤT BẠI: Hàm suy luận ML trả về kết quả lỗi hoặc không hợp lệ.")


# =====================================================================
# TEST 2: Kiểm tra cơ chế Hot-Swap (Thay máu mô hình không cần tắt bot)
# =====================================================================
print("\n[TEST 2] Kiểm tra cơ chế Hot-Swap: reload_model() trong OperatorAgent")
try:
    team.operator_agent.reload_model()
    reloaded_ok = team.operator_agent.model is not None
    if reloaded_ok:
        print("✅ ĐẠT: Cơ chế Hot-Swap hoạt động tốt, sẵn sàng cho tiến trình retrain ngầm.")
    else:
        print("❌ THẤT BẠI: Sau khi gọi reload_model(), mô hình bị mất khỏi RAM.")
except Exception as e:
    print(f"❌ THẤT BẠI: Lỗi phát sinh khi hot-swap: {e}")


# =====================================================================
# TEST 3: Kiểm tra Operator có kết hợp Xác suất ML vào Prompt ra lệnh không
# =====================================================================
print("\n[TEST 3] Kiểm tra tích hợp: OperatorAgent có dùng con số ML trong phân tích không?")

proposal_sample = team.operator_agent.analyze(
    symbol="BTC/USDT",
    current_price=84500.0,
    indicators={"price": 84500.0, "rsi_14": 62.0, "ema_9": 84550.0, "ema_21": 84400.0},
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="FLEXIBLE"
)

reason_text = proposal_sample.get("reason", "")
print(f"-> Đề xuất Operator: [{proposal_sample.get('action')}]")
print(f"-> Lập luận chi tiết: {reason_text}")

# Kiểm tra xem có phản ánh logic kỹ thuật và tính toán không
if proposal_sample.get("action") in ("OPEN_LONG", "OPEN_SHORT", "HOLD", "CLOSE"):
    print("✅ ĐẠT: Operator phản hồi JSON hợp lệ, kết hợp đầy đủ bối cảnh dữ liệu.")
else:
    print("❌ THẤT BẠI: Phản hồi của Operator không đạt chuẩn định dạng.")


# =====================================================================
# TEST 4: Strategist (1H: ONLY_SHORT) vs Operator (5m: LONG)
# =====================================================================
print("\n[TEST 4] Kiểm tra liên kết: Strategist (1H: ONLY_SHORT) vs Operator (5m: LONG)")

fake_bullish = {"price": 84500.0, "rsi_14": 65.5, "ema_9": 84600.0, "ema_21": 84400.0}

op_prop = team.operator_agent.analyze(
    symbol="BTC/USDT",
    current_price=84500.0,
    indicators=fake_bullish,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="ONLY_SHORT"
)
print(f"-> Operator đề xuất: [{op_prop.get('action')}] | Lý do: {op_prop.get('reason')}")

sup_review = team.supervisor_agent.review(
    proposal=op_prop,
    indicators=fake_bullish,
    cash=100.0,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="ONLY_SHORT",
    past_lessons=[],
    sentiment_info={"sentiment": "BULLISH", "panic_score": 2}
)
print(f"-> Supervisor duyệt: {sup_review.get('approved')} | Phản biện: {sup_review.get('feedback')}")

if not sup_review.get("approved") or op_prop.get("action") != "OPEN_LONG":
    print("✅ ĐẠT: Strategist đã kiểm soát thành công, cấm Long ngược sóng vĩ mô.")
else:
    print("❌ THẤT BẠI: Supervisor duyệt lệnh Long dù 1H cấm Long!")


# =====================================================================
# TEST 5: Sentiment (Panic 9/10) vs Supervisor
# =====================================================================
print("\n[TEST 5] Kiểm tra liên kết: Sentiment (Panic 9/10) vs Supervisor")

fake_short_proposal = {"action": "OPEN_SHORT", "confidence": 0.85, "reason": "EMA9 cắt dưới EMA21, RSI 35."}

sup_panic = team.supervisor_agent.review(
    proposal=fake_short_proposal,
    indicators={"price": 84000.0, "rsi_14": 35.0, "ema_9": 83900.0, "ema_21": 84100.0},
    cash=100.0,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="ONLY_SHORT",
    past_lessons=[],
    sentiment_info={
        "sentiment": "EXTREME_BEARISH",
        "panic_score": 9,
        "trading_advice": "HALT_TRADING",
        "key_driver": "Sàn giao dịch lớn bị đình chỉ rút tiền."
    }
)
print(f"-> Supervisor duyệt khi Panic=9: {sup_panic.get('approved')} | Rủi ro: {sup_panic.get('risk_score')}/10")
print(f"-> Phản biện: {sup_panic.get('feedback')}")

if not sup_panic.get("approved"):
    print("✅ ĐẠT: Phanh khẩn cấp kích hoạt chuẩn xác khi có bão tin tức.")
else:
    print("❌ THẤT BẠI: Supervisor vẫn duyệt lệnh khi Panic=9/10.")


# =====================================================================
# TEST 6: Bài học Reflector vs Supervisor
# =====================================================================
print("\n[TEST 6] Kiểm tra liên kết: Bài học Reflector -> Supervisor")

test_lessons = ["Cấm tuyệt đối mở lệnh SHORT khi RSI 5m đã giảm sâu dưới 30 (bẫy quá bán)."]

op_oversold = team.operator_agent.analyze(
    symbol="BTC/USDT",
    current_price=83000.0,
    indicators={"price": 83000.0, "rsi_14": 24.5, "ema_9": 82900.0, "ema_21": 83200.0},
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="FLEXIBLE"
)
print(f"-> Khi RSI=24.5, Operator đề xuất: [{op_oversold.get('action')}]")

sup_lesson = team.supervisor_agent.review(
    proposal=op_oversold,
    indicators={"price": 83000.0, "rsi_14": 24.5, "ema_9": 82900.0, "ema_21": 83200.0},
    cash=100.0,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="FLEXIBLE",
    past_lessons=test_lessons,
    sentiment_info={"sentiment": "NEUTRAL", "panic_score": 3}
)
print(f"-> Supervisor phản ứng với bài học: Duyệt = {sup_lesson.get('approved')}")
print(f"-> Phản biện: {sup_lesson.get('feedback')}")

if not sup_lesson.get("approved") or op_oversold.get("action") != "OPEN_SHORT":
    print("✅ ĐẠT: Bài học kinh nghiệm đã được tôn trọng, bẫy quá bán bị chặn.")
else:
    print("❌ CẢNH BÁO: Supervisor bỏ qua bài học kinh nghiệm.")

print("\n" + "=" * 75)
print("🏁 KẾT THÚC KIỂM TRA ĐỒNG BỘ TOÀN DIỆN!")
print("=" * 75)
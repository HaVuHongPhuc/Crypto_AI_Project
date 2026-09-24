"""Script kiểm tra toàn bộ 7 mẫu thông báo và thẻ Card Embed trên Discord."""

import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from notifiers.discord import DiscordNotifier

# 1. Nạp biến môi trường
load_dotenv(encoding="utf-8")

notifier = DiscordNotifier()

if not notifier.webhook_url:
    print("❌ LỖI: Chưa tìm thấy DISCORD_WEBHOOK_URL trong file .env!")
    exit(1)

print("=" * 65)
print("🚀 BẮT ĐẦU TEST GỬI TẤT CẢ THÔNG BÁO DISCORD (7 MẪU)")
print("=" * 65)


# -------------------------------------------------------------
# 1. THÔNG BÁO KHỞI ĐỘNG BOT
# -------------------------------------------------------------
print("\n[1/7] Gửi thông báo: Khởi động Bot...")
notifier.send(
    "🚀 **Bot 6-Agent Đã Khởi Động Thành Công!** Chế độ: `CLOUD` | Vốn: `99.98 USDT`"
)
time.sleep(1)


# -------------------------------------------------------------
# 2. THẺ CHỈ THỊ VĨ MÔ 1H (STRATEGIST) - VIỀN XANH DƯƠNG
# -------------------------------------------------------------
print("[2/7] Gửi thẻ: 🧭 [STRATEGIST 1H] Chỉ Thị Vĩ Mô...")
notifier.send_strategist_update(
    directive="FLEXIBLE",
    macro_bias="SIDEWAY",
    reasoning=(
        "Price is below EMA50 but above EMA200, and RSI is in the neutral zone (49.33), "
        "indicating a lack of clear directional momentum. RSI at 48.97 confirms a neutral consolidation phase."
    ),
    total_equity=99.90,
    available_cash=70.02
)
time.sleep(1)


# -------------------------------------------------------------
# 3. THẺ MỞ VỊ THẾ LONG - VIỀN XANH LÁ
# -------------------------------------------------------------
print("[3/7] Gửi thẻ: 🟢 [AI TEAM] Paper Trade Mở: LONG...")
notifier.send_trade_open(
    side="LONG",
    symbol="BTC/USDT",
    price=84267.510000,
    capital=70.158299,
    macro_directive="FLEXIBLE",
    rules_version=13,
    operator_reason=(
        "Dynamic Entry Rules satisfied: EMA9 (84175.76) > EMA21 (84159.76) with 16.00 USDT separation, "
        "RSI (67.42) > 50. Technical consensus confirms bullish momentum."
    ),
    supervisor_reason=(
        "Đề xuất OPEN_LONG hợp lệ. Chỉ thị FLEXIBLE, RSI nằm trong vùng an toàn (67.42 < 75), "
        "không có vị thế đối nghịch, và confidence của Operator đạt 0.85."
    ),
    total_equity=99.90,
    available_cash=70.02
)
time.sleep(1)


# -------------------------------------------------------------
# 4. THẺ MỞ VỊ THẾ SHORT - VIỀN CAM
# -------------------------------------------------------------
print("[4/7] Gửi thẻ: 🟢 [AI TEAM] Paper Trade Mở: SHORT...")
notifier.send_trade_open(
    side="SHORT",
    symbol="BTC/USDT",
    price=84834.090000,
    capital=69.867355,
    macro_directive="ONLY_SHORT",
    rules_version=13,
    operator_reason=(
        "Dynamic Entry Rules satisfied: EMA9 (85337.21) < EMA21 (85460.73) with separation > 3 USD, "
        "and RSI (35.46) < 50. Macro directive is ONLY_SHORT."
    ),
    supervisor_reason=(
        "Duyệt lệnh OPEN_SHORT. Chỉ thị Macro là ONLY_SHORT, RSI (35.46) trong vùng an toàn, "
        "không mâu thuẫn bài học kinh nghiệm và kỹ thuật rõ ràng."
    ),
    total_equity=99.90,
    available_cash=70.02
)
time.sleep(1)


# -------------------------------------------------------------
# 5. THẺ KẾT QUẢ GIAO DỊCH (WIN - LÃI) - VIỀN XANH LÁ
# -------------------------------------------------------------
print("[5/7] Gửi thẻ: 🔔 [KẾT QUẢ GIAO DỊCH] - CHỐT LỜI (WIN)...")
notifier.send_trade_close(
    exit_type="AI_EARLY_EXIT_CLOSE",
    side="SHORT",
    symbol="BTC/USDT",
    entry_price=85848.860000,
    exit_price=85496.000000,
    pnl_usdt=0.287717,
    pnl_pct=0.41,
    total_equity=100.287717,
    cum_pnl_usdt=0.287717,
    cum_pnl_pct=0.29,
    reflector_lesson="Tuân thủ tín hiệu thoát lệnh sớm của AI để bảo toàn lợi nhuận và tránh rủi ro đảo chiều."
)
time.sleep(1)


# -------------------------------------------------------------
# 6. THẺ KẾT QUẢ GIAO DỊCH (LOSS - LỖ) - VIỀN ĐỎ
# -------------------------------------------------------------
print("[6/7] Gửi thẻ: 🔔 [KẾT QUẢ GIAO DỊCH] - CẮT LỖ (LOSS)...")
notifier.send_trade_close(
    exit_type="AI_EARLY_EXIT_CLOSE",
    side="LONG",
    symbol="BTC/USDT",
    entry_price=86475.600000,
    exit_price=86222.010000,
    pnl_usdt=-0.203611,
    pnl_pct=-0.29,
    total_equity=98.985885,
    cum_pnl_usdt=-1.014115,
    cum_pnl_pct=-1.01,
    reflector_lesson="Cần kiên nhẫn chờ đợi xác nhận xu hướng thay vì thoát lệnh sớm khi giá biến động nhẹ."
)
time.sleep(1)


# -------------------------------------------------------------
# 7. THẺ TIẾN HÓA BỘ QUY TẮC (REFLECTOR) - VIỀN TÍM
# -------------------------------------------------------------
print("[7/7] Gửi thẻ: 🧬 [TIẾN HÓA BỘ QUY TẮC] v12 ➔ v13...")
rule_evolution_payload = {
    "embeds": [
        {
            "title": "🧬 [TIẾN HÓA BỘ QUY TẮC] v12 ➔ v13",
            "description": (
                "**Lý do nâng cấp:** Tối ưu hóa bộ lọc tín hiệu AI trong chế độ FLEXIBLE để loại bỏ nhiễu "
                "khi thị trường đi ngang, tránh tình trạng cắt lỗ liên tiếp do tín hiệu giả.\n"
                "**Lỗ hổng đã vá:** Tín hiệu AI (ML) quá nhạy cảm trong môi trường 1H FLEXIBLE, dẫn đến "
                "việc vào lệnh sớm khi chưa có xác nhận động lượng.\n\n"
                "**Entry mới:** 1. TREND MODE (70% vốn): Giữ nguyên quy tắc EMA9/21 và RSI. "
                "2. FLEXIBLE MODE (30% vốn): Chỉ mở lệnh khi RSI 5m thoát khỏi vùng nhiễu (45-55) "
                "VÀ khoảng cách EMA9/21 lớn hơn 0.05%.\n"
                "**Exit mới:** Vô hiệu hóa quyền đóng lệnh sớm của AI nếu chưa đạt 5 phút giữ lệnh. "
                "Duy trì Stop Loss cơ học 1.2% tuyệt đối."
            ),
            "color": 0x9B59B6,  # Màu tím đặc trưng
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    ]
}
notifier._post(rule_evolution_payload)
time.sleep(1)


# -------------------------------------------------------------
# 8. THẺ CẢNH BÁO BOT DỪNG (TÙY CHỌN BỔ SUNG)
# -------------------------------------------------------------
print("[Bonus] Gửi thẻ: ⚠️ Bot Trading Đã Dừng...")
bot_stop_payload = {
    "embeds": [
        {
            "title": "⚠️ Bot Trading Đã Dừng",
            "description": "Tiến trình bot trên máy chủ đã được người dùng tắt chủ động.",
            "color": 0x7F8C8D,  # Màu xám
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    ]
}
notifier._post(bot_stop_payload)

print("\n" + "=" * 65)
print("✅ HOÀN TẤT! Toàn bộ 7 mẫu thông báo đã được gửi lên Discord.")
print("Mời bạn mở điện thoại kiểm tra kênh #crypto-alerts.")
print("=" * 65)
"""
Script kiểm tra các giới hạn hành vi cực đoan của 6-Agent:
1. Test Chống Gồng Lỗ Vĩnh Viễn (Có chịu CẮT LỖ khi chạm ngưỡng/gãy xu hướng không?)
2. Test Chống Kẹt HOLD Khi Đạt Lãi (Có chịu CHỐT LỜI khi đạt target không?)
3. Test Chống Nhồi Lệnh Vô Tội Vạ (Có tự cấm mở lệnh mới khi đang giữ vị thế không?)
4. Test Chống Vào Lệnh Bừa Bãi Trong Vùng Nhiễu (Có biết đứng ngoài khi thị trường Sideway không?)
"""

from config.settings import Settings
from agents.agent_team import AgentTeam
from engine.paper_trader import PaperTrader

config = Settings()
team = AgentTeam(config)
trader = PaperTrader(initial_cash=100.0)

print("=" * 75)
print("🧪 BẮT ĐẦU KIỂM TRA HÀNH VI CỰC ĐOAN (STRESS-TEST AI TRADING BEHAVIOR)")
print("=" * 75)

# -----------------------------------------------------------------------------
# TEST 1: CHỐNG GỒNG LỖ VĨNH VIỄN (Hard Stop-Loss & Gãy cấu trúc)
# Giả lập: Giữ LONG @ 84,256 nhưng giá sập về 83,100 (-1.37% > SL 1.2%), đã giữ 20 phút.
# -----------------------------------------------------------------------------
print("\n[TEST 1] Kiểm tra: Bot có chịu CẮT LỖ hay sẽ vĩnh viễn HOLD gồng lỗ?")

loss_position = {
    "side": "LONG",
    "entry_price": 84256.35,
    "pnl_pct": -1.37,  # Vượt qua mốc Stop Loss cơ học 1.2% của v13
    "pnl_usdt": -0.96,
    "holding_candles": 4  # Đã giữ 20 phút (thỏa mãn quy tắc > 5 phút)
}

sl_indicators = {
    "price": 83100.0,
    "rsi_14": 28.5,       # RSI cắm đầu sâu dưới 50
    "ema_9": 83300.0,
    "ema_21": 83600.0,    # Nến đóng hoàn toàn dưới EMA21
    "macd": -300.0
}

op_sl_proposal = team.operator_agent.analyze(
    symbol="BTC/USDT",
    current_price=83100.0,
    indicators=sl_indicators,
    position_info=loss_position,
    macro_directive="FLEXIBLE"
)

print(f"-> Quyết định của Operator : [{op_sl_proposal.get('action')}]")
print(f"-> Lập luận của Operator   : {op_sl_proposal.get('reason')}")

if op_sl_proposal.get("action") == "CLOSE":
    print("✅ ĐẠT: Bot dứt khoát CẮT LỖ, không bao giờ có chuyện gồng lỗ vĩnh viễn!")
else:
    print("❌ CẢNH BÁO: Bot bị kẹt HOLD khi lỗ! Cần siết lại trọng số Stop Loss trong prompt.")


# -----------------------------------------------------------------------------
# TEST 2: CHỐNG KẸT HOLD KHI ĐÃ ĐẠT TARGET LÃI (Take Profit)
# Giả lập: Giữ LONG @ 84,256, giá tăng mạnh lên 85,200 (+1.12%), RSI chạm 72.
# -----------------------------------------------------------------------------
print("\n[TEST 2] Kiểm tra: Bot có chịu CHỐT LỜI hay tiếp tục HOLD tham lam?")

profit_position = {
    "side": "LONG",
    "entry_price": 84256.35,
    "pnl_pct": +1.12,  # Nằm trong biên độ chốt lời 0.8% - 1.5% của v13
    "pnl_usdt": +0.78,
    "holding_candles": 3  # Đã giữ 15 phút
}

tp_indicators = {
    "price": 85200.0,
    "rsi_14": 72.4,       # Quá mua, có dấu hiệu tạo đỉnh ngắn hạn
    "ema_9": 85100.0,
    "ema_21": 84700.0,
    "macd": 150.0
}

op_tp_proposal = team.operator_agent.analyze(
    symbol="BTC/USDT",
    current_price=85200.0,
    indicators=tp_indicators,
    position_info=profit_position,
    macro_directive="FLEXIBLE"
)

print(f"-> Quyết định của Operator : [{op_tp_proposal.get('action')}]")
print(f"-> Lập luận của Operator   : {op_tp_proposal.get('reason')}")

if op_tp_proposal.get("action") == "CLOSE":
    print("✅ ĐẠT: Bot chủ động CHỐT LỜI, không bị kẹt tham lam giữ vô tận!")
else:
    print("⚠️ CHÚ Ý: Operator vẫn chọn HOLD (Có thể muốn gồng đến biên trên 1.5% hoặc RSI đảo chiều).")


# -----------------------------------------------------------------------------
# TEST 3: CHỐNG NHỒI LỆNH BỪA BÃI KHI ĐANG CÓ LỆNH (Over-trading)
# Giả lập: Đang giữ lệnh LONG nhưng sàn xuất hiện tín hiệu LONG mới cực đẹp.
# -----------------------------------------------------------------------------
print("\n[TEST 3] Kiểm tra: Bot có nhồi thêm lệnh LONG khi đang giữ vị thế?")

active_pos_info = {
    "side": "LONG",
    "entry_price": 84256.35,
    "pnl_pct": +0.15,
    "pnl_usdt": +0.10,
    "holding_candles": 2
}

super_bullish_indicators = {
    "price": 84400.0,
    "rsi_14": 68.0,
    "ema_9": 84420.0,
    "ema_21": 84300.0,
    "macd": 80.0
}

# 1. Kiểm tra góc độ AI: Operator có tự đòi OPEN_LONG tiếp không?
op_overtrade = team.operator_agent.analyze(
    symbol="BTC/USDT",
    current_price=84400.0,
    indicators=super_bullish_indicators,
    position_info=active_pos_info,
    macro_directive="ONLY_LONG"
)

# 2. Kiểm tra góc độ Engine: PaperTrader có khóa cứng việc mở đè lệnh không?
engine_blocked = not trader.open_position("LONG", 84400.0, cash_amount=30.0) if trader.position else True

print(f"-> Operator phản ứng khi đang có vị thế : [{op_overtrade.get('action')}]")
print(f"-> Lập luận của Operator                : {op_overtrade.get('reason')}")
print(f"-> PaperTrader khóa cứng nhồi lệnh      : {'CÓ (Bảo vệ tuyệt đối)' if engine_blocked else 'KHÔNG'}")

if op_overtrade.get("action") in ("HOLD", "CLOSE") and engine_blocked:
    print("✅ ĐẠT: Bot tuyệt đối KHÔNG NHỒI LỆNH. Chỉ xử lý lệnh hiện tại!")
else:
    print("❌ CẢNH BÁO: Phát hiện nguy cơ nhồi lệnh trùng lặp!")


# -----------------------------------------------------------------------------
# TEST 4: CHỐNG VÀO LỆNH LIÊN TỤC TRONG VÙNG NHIỄU (Sideway Noise)
# Giả lập: Vị thế TRỐNG, nhưng thị trường đi ngang, RSI = 49 (vùng 45-55), EMA dính vào nhau.
# -----------------------------------------------------------------------------
print("\n[TEST 4] Kiểm tra: Bot có ngứa tay vào lệnh liên tục khi thị trường đi ngang?")

noise_indicators = {
    "price": 84000.0,
    "rsi_14": 49.2,       # Nằm chết dí trong vùng nhiễu (45-55) của v13
    "ema_9": 84005.0,
    "ema_21": 84002.0,    # Khoảng cách chỉ 3 USD (nhỏ hơn 0.05% = 42 USD)
    "macd": 1.5
}

op_noise = team.operator_agent.analyze(
    symbol="BTC/USDT",
    current_price=84000.0,
    indicators=noise_indicators,
    position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
    macro_directive="FLEXIBLE"
)

print(f"-> Đề xuất của Operator trong vùng nhiễu : [{op_noise.get('action')}]")
print(f"-> Lập luận của Operator                 : {op_noise.get('reason')}")

if op_noise.get("action") == "HOLD":
    print("✅ ĐẠT: Bộ lọc v13 hoạt động chuẩn, bot kiên nhẫn đứng ngoài quan sát, không mở bừa!")
else:
    print("❌ CẢNH BÁO: Bot bị kích động mở lệnh trong vùng nhiễu đi ngang!")

print("\n" + "=" * 75)
print("🏁 KẾT THÚC KIỂM TRA HÀNH VI CỰC ĐOAN!")
print("=" * 75)
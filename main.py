"""CLI entry point for the 24/7 paper-trading loop with Multi-Agent (Operator, Supervisor, Auditor)."""

import logging
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

from config.settings import settings
from data.fetcher import MarketDataFetcher
from data.preprocessor import add_indicators
from engine.paper_trader import PaperTrader
from engine.risk_manager import RiskManager
from models.predictor import Predictor
from notifiers.discord import send_message
from agents.agent_team import OperatorAgent, SupervisorAgent, AuditorAgent

# Cấu hình logging: Ghi đồng thời ra cả file bot.log và màn hình console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("storage/bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

# Biến toàn cục theo dõi nến 15m gần nhất đã phân tích qua AI
LAST_PROCESSED_CANDLE_TS = None


def run_once(
    fetcher: MarketDataFetcher,
    predictor: Predictor,
    trader: PaperTrader,
    risk: RiskManager,
    operator: OperatorAgent,
    supervisor: SupervisorAgent,
) -> None:
    global LAST_PROCESSED_CANDLE_TS

    # 1. Thu thập dữ liệu nến mới nhất
    candles = fetcher.fetch_ohlcv(settings.symbol, settings.timeframe, settings.candle_limit)
    price = float(candles["close"].iloc[-1])
    current_candle_ts = int(candles["timestamp"].iloc[-1])

    equity = trader.equity(price)
    pos = trader.position

    # 2. Hiển thị trạng thái vị thế và Unrealized PnL thời gian thực
    if pos:
        if pos.side == "LONG":
            live_pnl_pct = ((price - pos.entry_price) / pos.entry_price) * 100
            live_pnl_usdt = (price - pos.entry_price) * pos.amount
        else:  # SHORT
            live_pnl_pct = ((pos.entry_price - price) / pos.entry_price) * 100
            live_pnl_usdt = (pos.entry_price - price) * pos.amount

        icon = "🟢" if live_pnl_pct >= 0 else "🔴"
        sign = "+" if live_pnl_pct >= 0 else ""
        pos_status = f"{pos.side} @ {pos.entry_price:,.6f} | {icon} {sign}{live_pnl_pct:.2f}% ({sign}{live_pnl_usdt:.6f} USDT)"
    else:
        pos_status = "TRỐNG"

    # =========================================================================
    # TẦNG 1: QUẢN TRỊ RỦI RO CỤC BỘ (CHẠY MỖI 60 GIÂY - 0 TOKEN GROQ)
    # =========================================================================
    exit_reason = risk.should_exit(trader.position, price) if trader.position else None
    if exit_reason and trader.position:
        closed_side = trader.position.side
        entry_price = trader.position.entry_price
        position_value = trader.position.value

        pnl = trader.close_position(price, exit_reason)
        trade_pnl_pct = (pnl / position_value) * 100 if position_value > 0 else 0.0

        total_pnl = trader.cash - settings.initial_cash
        roi_pct = (total_pnl / settings.initial_cash) * 100
        sign = "+" if total_pnl >= 0 else ""
        color = 0x2ECC71 if pnl >= 0 else 0xE74C3C

        logging.warning(">>> ĐÓNG VỊ THẾ BẮT BUỘC (%s): PnL = %+.6f USDT | Vốn: %.6f USDT", exit_reason, pnl, trader.cash)
        if settings.discord_webhook_url:
            send_message(
                settings.discord_webhook_url,
                f"🔔 [KẾT QUẢ GIAO DỊCH] {exit_reason}",
                f"**Cặp:** {settings.symbol} | **Vị thế:** {closed_side}\n"
                f"**Giá vào:** {entry_price:,.6f} ➔ **Giá đóng:** {price:,.6f}\n"
                f"────────────────────────\n"
                f"💵 **Lãi/Lỗ lệnh này:** `{pnl:+.6f} USDT` ({trade_pnl_pct:+.2f}%)\n"
                f"💰 **TỔNG VỐN HIỆN TẠI:** `{trader.cash:,.6f} USDT`\n"
                f"📈 **TỔNG LÃI/LỖ TÍCH LŨY:** `{sign}{total_pnl:.6f} USDT` ({sign}{roi_pct:.2f}%)",
                color,
            )
        return

    # =========================================================================
    # TẦNG 2: KIỂM TRA ĐÓNG NẾN (CHỈ ĐÁNH THỨC OPERATOR & SUPERVISOR KHI CÓ NẾN MỚI)
    # =========================================================================
    if LAST_PROCESSED_CANDLE_TS == current_candle_ts:
        # Nếu vẫn trong cùng cây nến 15m: Chỉ in dòng trạng thái đếm giây, KHÔNG gọi Groq API
        now_str = datetime.now().strftime("%H:%M:%S")
        print(f"[{now_str}] ⏳ Theo dõi nến 15m | Giá: {price:,.6f} USDT | Vốn: {equity:,.6f} USDT | {pos_status}", end="\r")
        return

    # Khi bước sang cây nến 15m mới
    LAST_PROCESSED_CANDLE_TS = current_candle_ts
    candle_time_str = datetime.fromtimestamp(current_candle_ts / 1000, tz=timezone.utc).strftime("%H:%M UTC")
    print(f"\n\n🔔 [{datetime.now().strftime('%H:%M:%S')}] PHÁT HIỆN NẾN 15M MỚI ({candle_time_str}) ➔ KÍCH HOẠT AI TEAM...")

    # Trích xuất đặc trưng kỹ thuật & Tín hiệu ML nội bộ
    features = add_indicators(candles)
    ml_signal = predictor.predict(features)

    last_row = features.iloc[-1]
    indicators = {
        "rsi_14": round(float(last_row.get("rsi_14", 50)), 2),
        "macd": round(float(last_row.get("macd", 0)), 4),
        "macd_signal": round(float(last_row.get("macd_signal", 0)), 4),
        "ema_9": round(float(last_row.get("ema_9", price)), 2),
        "ema_21": round(float(last_row.get("ema_21", price)), 2),
        "volume_change": round(float(last_row.get("volume_change", 0)), 2),
        "ml_model_prediction": ml_signal.get("action", "HOLD"),
    }

    # 3. AI 1 (OPERATOR): Đề xuất kế hoạch
    proposal = operator.analyze(settings.symbol, price, indicators)
    action = proposal.get("action", "HOLD")
    confidence = proposal.get("confidence", 0.0)

    # 4. AI 2 (SUPERVISOR): Thẩm định rủi ro
    review = supervisor.review(proposal, indicators, trader.cash)
    is_approved = review.get("approved", False)
    risk_score = review.get("risk_score", 1)

    # =========================================================================
    # KHỐI HIỂN THỊ ĐỐI THOẠI VÀ SUY NGHĨ CỦA 2 AI TRÊN TERMINAL
    # =========================================================================
    print("\n" + "═" * 75)
    print(f"📊 [{datetime.now().strftime('%H:%M:%S')}] {settings.symbol} | Giá: {price:,.6f} USDT | Vốn: {equity:,.6f} USDT")
    print(f"   Vị thế: {pos_status}")
    print(f"   Chỉ báo: RSI(14)={indicators['rsi_14']} | MACD={indicators['macd']} | EMA9={indicators['ema_9']} | ML={indicators['ml_model_prediction']}")
    print("─" * 75)
    print(f"🤖 [OPERATOR]   : Đề xuất -> {action} (Độ tin cậy: {confidence * 100:.0f}%)")
    print(f"   Lập luận     : {proposal.get('reason', 'Không có phân tích chi tiết')}")
    print(f"🛡️  [SUPERVISOR] : Quyết định -> {'✅ DUYỆT' if is_approved else '❌ CHẶN/TỪ CHỐI'} (Mức rủi ro: {risk_score}/10)")
    print(f"   Phản biện    : {review.get('feedback', 'Không có phản biện')}")
    print("═" * 75 + "\n")
    # =========================================================================

    # 5. Mở vị thế mới (LONG hoặc SHORT)
    if not trader.position and is_approved and action in ("OPEN_LONG", "OPEN_SHORT"):
        side = "LONG" if action == "OPEN_LONG" else "SHORT"
        value = risk.position_value(trader.cash)
        if trader.open_position(settings.symbol, side, price, value):
            logging.info(">>> [AI TEAM] MỞ VỊ THẾ %s: Giá = %.6f, Vốn = %.6f USDT", side, price, value)
            if settings.discord_webhook_url:
                send_message(
                    settings.discord_webhook_url,
                    f"🟢 [AI TEAM] Paper Trade Mở: {side}",
                    f"**Cặp:** {settings.symbol} @ {price:,.6f}\n"
                    f"**Vị thế:** {side}\n"
                    f"**Khối lượng:** {value:,.6f} USDT\n"
                    f"**Operator:** {proposal.get('reason', 'N/A')}\n"
                    f"**Supervisor:** {review.get('feedback', 'Đã duyệt rủi ro')}",
                    0x2ECC71 if side == "LONG" else 0xE67E22,
                )

    # 6. Đóng vị thế chủ động theo tín hiệu đảo chiều từ AI
    elif trader.position and is_approved and action == "CLOSE":
        closed_side = trader.position.side
        entry_price = trader.position.entry_price
        position_value = trader.position.value

        pnl = trader.close_position(price, "SIGNAL_CLOSE")
        trade_pnl_pct = (pnl / position_value) * 100 if position_value > 0 else 0.0

        total_pnl = trader.cash - settings.initial_cash
        roi_pct = (total_pnl / settings.initial_cash) * 100
        sign = "+" if total_pnl >= 0 else ""
        color = 0x2ECC71 if pnl >= 0 else 0xE74C3C

        logging.info(">>> [AI TEAM] ĐÓNG VỊ THẾ CHỦ ĐỘNG: PnL = %+.6f USDT | Vốn: %.6f USDT", pnl, trader.cash)
        if settings.discord_webhook_url:
            send_message(
                settings.discord_webhook_url,
                "🟡 [AI TEAM] Paper Trade Đóng: Tín Hiệu Đảo Chiều",
                f"**Cặp:** {settings.symbol} | **Vị thế:** {closed_side}\n"
                f"**Giá vào:** {entry_price:,.6f} ➔ **Giá đóng:** {price:,.6f}\n"
                f"────────────────────────\n"
                f"💵 **Lãi/Lỗ lệnh này:** `{pnl:+.6f} USDT` ({trade_pnl_pct:+.2f}%)\n"
                f"💰 **TỔNG VỐN HIỆN TẠI:** `{trader.cash:,.6f} USDT`\n"
                f"📈 **TỔNG LÃI/LỖ TÍCH LŨY:** `{sign}{total_pnl:.6f} USDT` ({sign}{roi_pct:.2f}%)\n"
                f"**Lý do AI:** {proposal.get('reason', 'Chốt theo tín hiệu đảo chiều')}",
                color,
            )


def main() -> None:
    fetcher = MarketDataFetcher(settings.exchange_id)
    predictor = Predictor()
    trader = PaperTrader(settings.initial_cash)
    risk = RiskManager(
        position_size_pct=settings.position_size_pct,
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
        trailing_stop_pct=settings.trailing_stop_pct,
        trailing_activation_pct=settings.trailing_activation_pct,
    )

    # Khởi tạo 3 Agent
    operator = OperatorAgent()
    supervisor = SupervisorAgent()
    auditor = AuditorAgent()

    campaign_end = datetime.now(timezone.utc) + timedelta(days=settings.campaign_days)

    print("=" * 75)
    print("   CRYPTO AI MULTI-AGENT PAPER TRADING BOT (OPERATOR - SUPERVISOR - AUDITOR)")
    print(f"   Cặp: {settings.symbol} | Khung: {settings.timeframe} | Chu kỳ quét: {settings.loop_seconds}s")
    print(f"   Vốn khởi điểm: {settings.initial_cash:,.6f} USDT")
    print(f"   Chiến dịch: {settings.campaign_days} ngày, kết thúc vào {campaign_end.isoformat()}")
    print("=" * 75)

    if settings.discord_webhook_url:
        send_message(
            settings.discord_webhook_url,
            "🚀 Multi-Agent Bot Khởi Động Thành Công",
            f"**Thị trường:** {settings.symbol} ({settings.exchange_id.upper()})\n"
            f"**Hệ thống:** Operator (Trader) + Supervisor (Risk) + Auditor (SRE)\n"
            f"**Vốn giả lập:** {settings.initial_cash:,.6f} USDT\n"
            f"**Chiến dịch:** {settings.campaign_days} ngày",
            0x3498DB,
        )

    while datetime.now(timezone.utc) < campaign_end:
        try:
            run_once(fetcher, predictor, trader, risk, operator, supervisor)
        except Exception:
            error_trace = traceback.format_exc()
            logging.exception("Vòng lặp gặp ngoại lệ nghiêm trọng!")

            # AI 3 (AUDITOR): Phân tích traceback lỗi và gửi chẩn đoán thông minh về Discord
            report = auditor.inspect_error(error_trace)
            severity = report.get("severity", "WARNING")
            diagnosis = report.get("diagnosis", "Lỗi không xác định")
            action_suggested = report.get("suggested_action", "Chờ vòng quét tiếp theo")

            if settings.discord_webhook_url:
                send_message(
                    settings.discord_webhook_url,
                    f"⚠️ [AUDITOR ALERT] Sự cố: {severity}",
                    f"**Chẩn đoán:** {diagnosis}\n**Đề xuất:** {action_suggested}",
                    0xE74C3C,
                )

        remaining_seconds = (campaign_end - datetime.now(timezone.utc)).total_seconds()
        if remaining_seconds > 0:
            time.sleep(min(settings.loop_seconds, remaining_seconds))

    logging.info("Chiến dịch kết thúc. Tiền mặt cuối: %.6f USDT", trader.cash)
    if settings.discord_webhook_url:
        send_message(
            settings.discord_webhook_url,
            "🏁 Chiến dịch Paper Trading Đã Kết Thúc",
            f"**Thời lượng:** {settings.campaign_days} ngày\n**Vốn cuối cùng:** {trader.cash:,.6f} USDT",
            0x9B59B6,
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nĐã nhận lệnh tắt bot từ bàn phím (Ctrl + C). Tạm dừng hệ thống.")
        if settings.discord_webhook_url:
            send_message(
                settings.discord_webhook_url,
                "⚠️ Bot Trading Đã Dừng",
                "Tiến trình bot trên máy chủ đã được người dùng tắt chủ động.",
                0x95A5A6,
            )
        print("Bot đã dừng.")
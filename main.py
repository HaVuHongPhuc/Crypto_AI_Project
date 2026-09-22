"""CLI entry point for the 24/7 paper-trading loop with 5-Agent Architecture:
(Strategist - Operator - Supervisor - Reflector - Auditor)
Tích hợp cơ chế tự học và tự động cập nhật bộ luật chiến thuật (Self-Improving).
"""

from datetime import datetime, timedelta, timezone
import logging
import sys
import time
import traceback

from agents.agent_team import (
    AuditorAgent,
    OperatorAgent,
    ReflectorAgent,
    StrategistAgent,
    SupervisorAgent,
)
from config.settings import settings
from data.fetcher import MarketDataFetcher
from data.preprocessor import add_indicators
from engine.paper_trader import PaperTrader
from engine.risk_manager import RiskManager
from models.predictor import Predictor
from notifiers.discord import send_message

# Cấu hình logging: Ghi đồng thời ra cả file bot.log và màn hình console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("storage/bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

# Biến toàn cục theo dõi nến 5m, chu kỳ nến 1H, số nến gồng và lịch sử lệnh trong phiên
LAST_PROCESSED_CANDLE_TS = None
LAST_STRATEGIST_HOUR = None
HOLDING_CANDLES_COUNT = 0
CURRENT_MACRO = {
    "directive": "FLEXIBLE",
    "macro_bias": "SIDEWAY",
    "reasoning": "Khởi tạo hệ thống",
}
RECENT_TRADES_HISTORY = []


def update_macro_strategy(
    fetcher: MarketDataFetcher, strategist: StrategistAgent, current_price: float
) -> None:
  """Cập nhật xu hướng khung 1H một lần mỗi giờ từ StrategistAgent."""
  global LAST_STRATEGIST_HOUR, CURRENT_MACRO
  current_hour = datetime.now(timezone.utc).hour

  if LAST_STRATEGIST_HOUR != current_hour:
    try:
      candles_1h = fetcher.fetch_ohlcv(settings.symbol, "1h", 250)
      if candles_1h is not None and not candles_1h.empty:
        df_1h = add_indicators(candles_1h)

        if "ema_50" in df_1h.columns:
          ema_50 = float(df_1h["ema_50"].iloc[-1])
        else:
          ema_50 = float(
              df_1h["close"].ewm(span=50, adjust=False).mean().iloc[-1]
          )

        if "ema_200" in df_1h.columns:
          ema_200 = float(df_1h["ema_200"].iloc[-1])
        else:
          ema_200 = float(
              df_1h["close"].ewm(span=200, adjust=False).mean().iloc[-1]
          )

        last_h1 = df_1h.iloc[-1]
        h1_ind = {
            "rsi_14": round(float(last_h1.get("rsi_14", 50)), 2),
            "macd": round(float(last_h1.get("macd", 0)), 4),
            "ema_50": round(ema_50, 2),
            "ema_200": round(ema_200, 2),
        }

        macro_res = strategist.analyze_macro(
            settings.symbol, current_price, h1_ind
        )

        # CHỈ CẬP NHẬT KHI AI PHÂN TÍCH HỢP LỆ (Không gán None khi API gặp lỗi)
        if isinstance(macro_res, dict) and macro_res.get("directive"):
          CURRENT_MACRO = macro_res
          LAST_STRATEGIST_HOUR = current_hour

          logging.info(
              ">>> [STRATEGIST 1H] Chỉ thị: %s | Xu hướng: %s",
              CURRENT_MACRO.get("directive"),
              CURRENT_MACRO.get("macro_bias"),
          )
          if settings.discord_webhook_url:
            send_message(
                settings.discord_webhook_url,
                f"🧭 [STRATEGIST 1H] Chỉ Thị Vĩ Mô: {CURRENT_MACRO.get('directive')}",
                f"**Xu hướng 1H:** {CURRENT_MACRO.get('macro_bias')}\n"
                f"**Chiến lược:** {CURRENT_MACRO.get('reasoning')}",
                0x3498DB,
            )
        else:
          logging.warning(
              "Strategist 1H chưa có phản hồi hợp lệ (%s). Giữ chỉ thị: [%s] và"
              " sẽ thử lại ở nến tới.",
              macro_res,
              CURRENT_MACRO.get("directive", "FLEXIBLE"),
          )
    except Exception as e:
      logging.warning("Lỗi cập nhật Strategist 1H: %s", str(e))


def handle_trade_closing_and_evolution(
    trader: PaperTrader,
    reflector: ReflectorAgent,
    closed_side: str,
    entry_price: float,
    exit_price: float,
    position_value: float,
    exit_reason: str,
    color: int,
) -> None:
  """Xử lý đóng lệnh, rút kinh nghiệm và kích hoạt Reflector tự nâng cấp bộ luật."""
  global RECENT_TRADES_HISTORY, HOLDING_CANDLES_COUNT

  pnl = trader.close_position(exit_price, exit_reason)
  trade_pnl_pct = (pnl / position_value) * 100 if position_value > 0 else 0.0

  total_pnl = trader.cash - settings.initial_cash
  roi_pct = (total_pnl / settings.initial_cash) * 100
  sign = "+" if total_pnl >= 0 else ""

  HOLDING_CANDLES_COUNT = 0  # Đặt lại số nến gồng về 0 khi đóng lệnh

  # 1. Đóng gói dữ liệu lệnh vừa kết thúc
  trade_summary = {
      "side": closed_side,
      "entry_price": entry_price,
      "exit_price": exit_price,
      "pnl_usdt": pnl,
      "pnl_pct": trade_pnl_pct,
      "exit_reason": exit_reason,
  }

  # 2. Reflector rút bài học ngắn hạn lưu vào memory.json
  lesson = reflector.reflect(trade_summary)
  trade_summary["lesson"] = lesson
  RECENT_TRADES_HISTORY.append(trade_summary)

  logging.info(
      ">>> ĐÓNG VỊ THẾ (%s): PnL = %+.6f USDT | Vốn: %.6f USDT",
      exit_reason,
      pnl,
      trader.cash,
  )

  # 3. Gửi thông báo kết quả giao dịch về Discord
  if settings.discord_webhook_url:
    send_message(
        settings.discord_webhook_url,
        f"🔔 [KẾT QUẢ GIAO DỊCH] {exit_reason}",
        f"**Cặp:** {settings.symbol} | **Vị thế:** {closed_side}\n"
        f"**Giá vào:** {entry_price:,.6f} ➔ **Giá đóng:** {exit_price:,.6f}\n"
        "────────────────────────\n"
        f"💵 **Lãi/Lỗ lệnh này:** `{pnl:+.6f} USDT` ({trade_pnl_pct:+.2f}%)\n"
        f"💰 **TỔNG VỐN HIỆN TẠI:** `{trader.cash:,.6f} USDT`\n"
        f"📈 **TỔNG LÃI/LỖ TÍCH LŨY:** `{sign}{total_pnl:.6f} USDT`"
        f" ({sign}{roi_pct:.2f}%)\n"
        f"🧠 **Bài học Reflector:** `{lesson}`",
        color,
    )

  # 4. KÍCH HOẠT TỰ TIẾN HÓA: Cứ sau mỗi 2 lệnh đóng, Reflector tự đánh giá và viết lại bộ luật
  if len(RECENT_TRADES_HISTORY) >= 2:
    old_rules = ReflectorAgent.load_rules()
    old_ver = old_rules.get("version", 1)

    new_rules = reflector.auto_evolve_rules(RECENT_TRADES_HISTORY)

    if new_rules.get("version", 1) > old_ver:
      logging.info(
          ">>> [AI TỰ NÂNG CẤP CHIẾN THUẬT] Đã tiến hóa lên phiên bản v%d",
          new_rules.get("version"),
      )
      if settings.discord_webhook_url:
        send_message(
            settings.discord_webhook_url,
            f"🧬 [AI TỰ TIẾN HÓA BỘ LUẬT] Đã Cập Nhật v{new_rules.get('version')}",
            f"**Lý do cải tiến:** {new_rules.get('reason_for_update')}\n"
            f"**Quy tắc thoát lệnh mới:** `{new_rules.get('exit_rules')}`",
            0x9B59B6,
        )


def run_once(
    fetcher: MarketDataFetcher,
    predictor: Predictor,
    trader: PaperTrader,
    risk: RiskManager,
    operator: OperatorAgent,
    supervisor: SupervisorAgent,
    strategist: StrategistAgent,
    reflector: ReflectorAgent,
) -> None:
  global LAST_PROCESSED_CANDLE_TS, HOLDING_CANDLES_COUNT

  # 1. Thu thập dữ liệu nến 5m mới nhất
  candles = fetcher.fetch_ohlcv(
      settings.symbol, settings.timeframe, settings.candle_limit
  )
  if candles is None or candles.empty:
    logging.warning("Dữ liệu nến từ sàn rỗng, bỏ qua chu kỳ này.")
    return

  price = float(candles["close"].iloc[-1])
  current_candle_ts = int(
      candles["timestamp"].iloc[-1]
      if "timestamp" in candles.columns
      else candles.index[-1]
  )

  equity = trader.equity(price)
  pos = trader.position

  # Cập nhật định hướng vĩ mô 1H
  update_macro_strategy(fetcher, strategist, price)

  # 2. Hiển thị trạng thái vị thế thời gian thực
  if pos:
    live_pnl_pct = (
        ((price - pos.entry_price) / pos.entry_price) * 100
        if pos.side == "LONG"
        else ((pos.entry_price - price) / pos.entry_price) * 100
    )
    live_pnl_usdt = (
        (price - pos.entry_price) * pos.amount
        if pos.side == "LONG"
        else (pos.entry_price - price) * pos.amount
    )
    icon = "🟢" if live_pnl_pct >= 0 else "🔴"
    sign = "+" if live_pnl_pct >= 0 else ""
    pos_status = (
        f"{pos.side} @ {pos.entry_price:,.6f} | {icon}"
        f" {sign}{live_pnl_pct:.2f}% ({sign}{live_pnl_usdt:.6f} USDT)"
    )
    position_info = {
        "side": pos.side,
        "entry_price": pos.entry_price,
        "pnl_pct": live_pnl_pct,
        "pnl_usdt": live_pnl_usdt,
        "amount": pos.amount,
        "holding_candles": HOLDING_CANDLES_COUNT,
    }
  else:
    HOLDING_CANDLES_COUNT = 0
    pos_status = "TRỐNG"
    position_info = {
        "side": "NONE",
        "entry_price": 0.0,
        "pnl_pct": 0.0,
        "pnl_usdt": 0.0,
        "amount": 0.0,
        "holding_candles": 0,
    }

  # =========================================================================
  # TẦNG 1: QUẢN TRỊ RỦI RO CỤC BỘ (Stop Loss / Trailing Stop)
  # =========================================================================
  exit_reason = risk.should_exit(trader.position, price) if trader.position else None
  if exit_reason and trader.position:
    closed_side = trader.position.side
    entry_price = trader.position.entry_price
    position_value = trader.position.value
    color = 0x2ECC71 if (price >= entry_price if closed_side == "LONG" else price <= entry_price) else 0xE74C3C

    handle_trade_closing_and_evolution(
        trader,
        reflector,
        closed_side,
        entry_price,
        price,
        position_value,
        exit_reason,
        color,
    )
    return

  # =========================================================================
  # TẦNG 2: KIỂM TRA ĐÓNG NẾN 5M
  # =========================================================================
  current_rules = ReflectorAgent.load_rules()
  rule_ver = current_rules.get("version", 1)

  if LAST_PROCESSED_CANDLE_TS == current_candle_ts:
    now_str = datetime.now().strftime("%H:%M:%S")
    print(
        f"[{now_str}] ⏳ Nến {settings.timeframe} | Giá: {price:,.6f} USDT |"
        f" 1H: [{CURRENT_MACRO.get('directive', 'FLEXIBLE')}] [Luật: v{rule_ver}] |"
        f" {pos_status}",
        end="\r",
    )
    return

  LAST_PROCESSED_CANDLE_TS = current_candle_ts
  if pos:
    HOLDING_CANDLES_COUNT += 1
    position_info["holding_candles"] = HOLDING_CANDLES_COUNT

  candle_time_str = datetime.fromtimestamp(
      current_candle_ts / 1000, tz=timezone.utc
  ).strftime("%H:%M UTC")
  print(
      f"\n\n🔔 [{datetime.now().strftime('%H:%M:%S')}] PHÁT HIỆN NẾN"
      f" {settings.timeframe.upper()} MỚI ({candle_time_str}) ➔ KÍCH HOẠT AI"
      " TEAM..."
  )

  # Trích xuất chỉ số kỹ thuật nến 5m
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
      "ml_signal": ml_signal.get("action", "HOLD"),
  }

  past_lessons = ReflectorAgent.load_lessons()

  # 3. AI OPERATOR: Phân tích theo bộ luật động hiện hành
  proposal = operator.analyze(
      settings.symbol,
      price,
      indicators,
      position_info=position_info,
      macro_directive=CURRENT_MACRO.get("directive", "FLEXIBLE"),
  )
  action = proposal.get("action", "HOLD")
  confidence = proposal.get("confidence", 0.0)

  # 4. AI SUPERVISOR: Thẩm định rủi ro
  review = supervisor.review(
      proposal,
      indicators,
      trader.cash,
      position_info=position_info,
      macro_directive=CURRENT_MACRO.get("directive", "FLEXIBLE"),
      past_lessons=past_lessons,
  )
  is_approved = review.get("approved", False)
  risk_score = review.get("risk_score", 1)

  # In nhật ký quyết định trên Console
  print("\n" + "═" * 75)
  print(
      f"📊 [{datetime.now().strftime('%H:%M:%S')}] {settings.symbol} | Giá:"
      f" {price:,.6f} USDT | Vốn: {equity:,.6f} USDT"
  )
  print(
      f"   Chỉ thị 1H: [{CURRENT_MACRO.get('directive', 'FLEXIBLE')}] | Bộ luật"
      f" đang chạy: [v{rule_ver}]"
  )
  print(f"   Vị thế: {pos_status}")
  print(
      f"   Chỉ báo: RSI(14)={indicators['rsi_14']} | MACD={indicators['macd']}"
      f" | EMA9={indicators['ema_9']}"
  )
  print("─" * 75)
  print(
      f"🤖 [OPERATOR]   : Đề xuất -> {action} (Độ tin cậy:"
      f" {confidence * 100:.0f}%)"
  )
  print(f"   Lập luận     : {proposal.get('reason', 'N/A')}")
  print(
      "🛡️  [SUPERVISOR] : Quyết định ->"
      f" {'✅ DUYỆT' if is_approved else '❌ TỪ CHỐI'} (Mức rủi ro:"
      f" {risk_score}/10)"
  )
  print(f"   Phản biện    : {review.get('feedback', 'N/A')}")
  print("═" * 75 + "\n")

  # 5. Mở vị thế mới khi vị thế đang TRỐNG
  if not trader.position and is_approved and action in ("OPEN_LONG", "OPEN_SHORT"):
    side = "LONG" if action == "OPEN_LONG" else "SHORT"
    value = risk.position_value(trader.cash)
    if trader.open_position(settings.symbol, side, price, value):
      HOLDING_CANDLES_COUNT = 1
      logging.info(
          ">>> [AI TEAM] MỞ VỊ THẾ %s: Giá = %.6f, Vốn = %.6f USDT",
          side,
          price,
          value,
      )
      if settings.discord_webhook_url:
        send_message(
            settings.discord_webhook_url,
            f"🟢 [AI TEAM] Paper Trade Mở: {side}",
            f"**Cặp:** {settings.symbol} @ {price:,.6f}\n"
            f"**Vị thế:** {side} | **Khối lượng:** {value:,.6f} USDT\n"
            f"**Chỉ thị 1H:** {CURRENT_MACRO.get('directive', 'FLEXIBLE')} |"
            f" **Bộ luật:** v{rule_ver}\n"
            f"**Operator:** {proposal.get('reason', 'N/A')}\n"
            f"**Supervisor:** {review.get('feedback', 'Đã duyệt rủi ro')}",
            0x2ECC71 if side == "LONG" else 0xE67E22,
        )

  # 6. Đóng vị thế chủ động theo tín hiệu đảo chiều từ AI
  elif trader.position and is_approved and (
      action in ("CLOSE", "CLOSE_LONG", "CLOSE_SHORT")
      or (trader.position.side == "SHORT" and action == "OPEN_LONG")
      or (trader.position.side == "LONG" and action == "OPEN_SHORT")
  ):
    closed_side = trader.position.side
    entry_price = trader.position.entry_price
    position_value = trader.position.value
    close_reason = f"AI_EARLY_EXIT_{action}"
    color = 0x2ECC71 if (price >= entry_price if closed_side == "LONG" else price <= entry_price) else 0xE74C3C

    handle_trade_closing_and_evolution(
        trader,
        reflector,
        closed_side,
        entry_price,
        price,
        position_value,
        close_reason,
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

  # Khởi tạo đầy đủ 5 Agent
  strategist = StrategistAgent()
  operator = OperatorAgent()
  supervisor = SupervisorAgent()
  reflector = ReflectorAgent()
  auditor = AuditorAgent()

  campaign_end = datetime.now(timezone.utc) + timedelta(
      days=settings.campaign_days
  )

  current_rules = ReflectorAgent.load_rules()
  print("=" * 75)
  print(
      "   CRYPTO AI 5-AGENT SELF-IMPROVING BOT (STRATEGIST - OPERATOR -"
      " SUPERVISOR - REFLECTOR - AUDITOR)"
  )
  print(
      f"   Cặp: {settings.symbol} | Khung: {settings.timeframe} | Phiên bản"
      f" luật: v{current_rules.get('version', 1)}"
  )
  print(f"   Vốn khởi điểm: {settings.initial_cash:,.6f} USDT")
  print(
      f"   Chiến dịch: {settings.campaign_days} ngày, kết thúc vào"
      f" {campaign_end.isoformat()}"
  )
  print("=" * 75)

  if settings.discord_webhook_url:
    send_message(
        settings.discord_webhook_url,
        "🚀 Multi-Agent Bot (5 Tác Tử Tự Tiến Hóa) Khởi Động Thành Công",
        f"**Thị trường:** {settings.symbol} ({settings.exchange_id.upper()})\n"
        f"**Phiên bản luật:** v{current_rules.get('version', 1)}\n"
        "**Cơ chế:** Tự động sửa đổi chiến thuật ra/vào lệnh khi phát hiện"
        " lỗi\n"
        f"**Vốn:** {settings.initial_cash:,.6f} USDT | **Chiến dịch:**"
        f" {settings.campaign_days} ngày",
        0x3498DB,
    )

  while datetime.now(timezone.utc) < campaign_end:
    try:
      run_once(
          fetcher,
          predictor,
          trader,
          risk,
          operator,
          supervisor,
          strategist,
          reflector,
      )
    except Exception:
      error_trace = traceback.format_exc()
      logging.exception("Vòng lặp gặp ngoại lệ nghiêm trọng!")

      report = auditor.inspect_error(error_trace)
      severity = report.get("severity", "WARNING")
      diagnosis = report.get("diagnosis", "Lỗi không xác định")
      action_suggested = report.get(
          "suggested_action", "Chờ vòng quét tiếp theo"
      )

      if settings.discord_webhook_url:
        send_message(
            settings.discord_webhook_url,
            f"⚠️ [AUDITOR ALERT] Sự cố: {severity}",
            f"**Chẩn đoán:** {diagnosis}\n**Đề xuất:** {action_suggested}",
            0xE74C3C,
        )

    remaining_seconds = (
        campaign_end - datetime.now(timezone.utc)
    ).total_seconds()
    if remaining_seconds > 0:
      time.sleep(min(settings.loop_seconds, remaining_seconds))

  logging.info("Chiến dịch kết thúc. Tiền mặt cuối: %.6f USDT", trader.cash)
  if settings.discord_webhook_url:
    send_message(
        settings.discord_webhook_url,
        "🏁 Chiến dịch Paper Trading Đã Kết Thúc",
        f"**Thời lượng:** {settings.campaign_days} ngày\n**Vốn cuối cùng:**"
        f" {trader.cash:,.6f} USDT",
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
"""Vòng lặp điều hành chính 6-Agent Crypto Scalping (BTC/USDT 5m)."""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from agents.agent_team import AgentTeam, ReflectorAgent
from config.settings import Settings
from engine.paper_trader import PaperTrader
from notifiers.discord import DiscordNotifier
import requests

# Thiết lập ghi log
LOG_FILE = Path("storage/bot.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


class Main:

  def __init__(self, config_path: str = None):
    # 1. Khởi tạo cấu hình và bộ nạp
    self.config = Settings()

    # 2. Khởi tạo PaperTrader và nạp vị thế cũ (nếu có)
    self.paper_trader = PaperTrader(initial_cash=100.0)

    # 3. Khởi tạo hệ thống 6 Tác tử
    self.agent_team = AgentTeam(self.config)

    # 4. Kênh thông báo Discord
    self.notifier = DiscordNotifier(self.config.discord_webhook_url)

    # 5. Các biến quản lý trạng thái
    self.symbol = "BTCUSDT"
    self.last_candle_time = None
    self.recent_closed_trades = []

  def load_active_position(self):
    """Khôi phục vị thế khi bot khởi động lại."""
    self.paper_trader.load_active_position()

  def save_active_position(self):
    """Lưu vị thế hiện tại ra ổ cứng chống sập nguồn."""
    self.paper_trader.save_active_position()

  def fetch_market_data(self) -> dict:
    """Lấy dữ liệu nến thực tế từ Binance Public API và tính toán chỉ báo kỹ thuật."""
    url = f"https://api.binance.com/api/v3/klines?symbol={self.symbol}&interval=5m&limit=50"
    try:
      res = requests.get(url, timeout=10)
      if res.status_code != 200:
        return {}
      klines = res.json()
      if not klines or len(klines) < 30:
        return {}

      closes = [float(k[4]) for k in klines]
      latest_candle = klines[-1]

      # Tính EMA
      def calc_ema(data, period):
        k = 2.0 / (period + 1)
        ema = [data[0]]
        for price in data[1:]:
          ema.append(price * k + ema[-1] * (1 - k))
        return ema[-1]

      ema9 = calc_ema(closes, 9)
      ema21 = calc_ema(closes, 21)

      # Tính RSI(14)
      gains, losses = [], []
      for i in range(1, 15):
        diff = closes[-i] - closes[-i - 1]
        if diff >= 0:
          gains.append(diff)
          losses.append(0.0)
        else:
          gains.append(0.0)
          losses.append(abs(diff))
      avg_gain = sum(gains) / 14.0
      avg_loss = sum(losses) / 14.0
      rsi14 = (
          100.0
          if avg_loss == 0
          else (100.0 - (100.0 / (1.0 + (avg_gain / avg_loss))))
      )

      # Cập nhật PnL nếu đang giữ lệnh
      current_price = float(latest_candle[4])
      if self.paper_trader.position:
        self.paper_trader.update_position(current_price)

      return {
          "open_time": latest_candle[0],
          "price": current_price,
          "rsi_14": round(rsi14, 2),
          "ema_9": round(ema9, 2),
          "ema_21": round(ema21, 2),
          "macd": round(ema9 - ema21, 4),
          "capital": round(self.paper_trader.cash, 2),
      }
    except Exception as e:
      logging.warning("Lỗi fetch market data: %s", e)
      return {}

  def print_dashboard(self, market_data: dict, sentiment: dict, rules: dict):
    """In bảng điều khiển trực quan theo từng nến."""
    pos = self.paper_trader.position
    pos_str = (
        f"{pos.side} @ {pos.entry_price:.2f} (PnL: {pos.pnl_pct:+.2f}%)"
        if pos
        else "TRỐNG"
    )

    print("\n" + "═" * 75)
    print(
        f"📊 [{time.strftime('%H:%M:%S')}] BTC/USDT: {market_data.get('price', 0):,.2f}"
        f" USDT | Vốn: {market_data.get('capital', 100):.2f} USDT"
    )
    print(
        f"   Tin tức: [{sentiment.get('sentiment', 'NEUTRAL')} (Panic:"
        f" {sentiment.get('panic_score', 5)}/10)] | Bộ luật:"
        f" [v{rules.get('version', 1)}]"
    )
    print(f"   Vị thế: {pos_str}")
    print(
        f"   Chỉ báo 5m: RSI(14)={market_data.get('rsi_14')} |"
        f" EMA9={market_data.get('ema_9')} | EMA21={market_data.get('ema_21')}"
    )
    print("─" * 75)

  def run(self):
    """Vòng lặp điều hành 24/7."""
    mode = self.config.llm_mode
    print("=" * 75)
    print(
        "   CRYPTO AI 6-AGENT SYSTEM (STRATEGIST - OPERATOR - SUPERVISOR -"
        " REFLECTOR - AUDITOR - SENTIMENT)"
    )
    print(f"   Cặp: BTC/USDT | Khung: 5m | Chế độ LLM: [{mode}]")
    print("=" * 75)

    self.load_active_position()
    self.notifier.send(
        f"🚀 **Bot 6-Agent Đã Khởi Động Thành Công!** Chế độ: `{mode}`"
    )

    while True:
      try:
        market_data = self.fetch_market_data()
        if not market_data:
          time.sleep(10)
          continue

        # Chỉ kích hoạt AI Team khi nến 5m mới mở cửa
        if market_data["open_time"] != self.last_candle_time:
          self.last_candle_time = market_data["open_time"]

          # 1. Thu thập dữ liệu tình báo & luật hiện hành
          sentiment_info = (
              self.agent_team.sentiment_agent.analyze_market_sentiment()
          )
          rules = ReflectorAgent.load_rules()

          # 2. In Dashboard
          self.print_dashboard(market_data, sentiment_info, rules)

          pos = self.paper_trader.position
          position_info = (
              {
                  "side": pos.side,
                  "entry_price": pos.entry_price,
                  "pnl_pct": pos.pnl_pct,
                  "pnl_usdt": pos.pnl_usdt,
                  "holding_candles": pos.holding_candles,
              }
              if pos
              else {"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0}
          )

          # 3. OPERATOR AGENT đề xuất
          proposal = self.agent_team.operator_agent.analyze(
              symbol="BTC/USDT",
              current_price=market_data["price"],
              indicators=market_data,
              position_info=position_info,
              macro_directive="FLEXIBLE",
          )
          conf_pct = int(proposal.get("confidence", 0.8) * 100)
          print(
              f"🤖 [OPERATOR]   : Đề xuất -> {proposal.get('action')} (Độ tin"
              f" cậy: {conf_pct}%)"
          )
          print(f"   Lập luận     : {proposal.get('reason')}")

          # 4. SUPERVISOR AGENT kiểm duyệt rủi ro
          past_lessons = ReflectorAgent.load_lessons(side=position_info["side"])
          review = self.agent_team.supervisor_agent.review(
              proposal=proposal,
              indicators=market_data,
              cash=self.paper_trader.cash,
              position_info=position_info,
              macro_directive="FLEXIBLE",
              past_lessons=past_lessons,
              sentiment_info=sentiment_info,
          )
          approved_icon = "✅ DUYỆT" if review.get("approved") else "❌ TỪ CHỐI"
          print(
              f"🛡️  [SUPERVISOR] : Quyết định -> {approved_icon} (Mức rủi ro:"
              f" {review.get('risk_score')}/10)"
          )
          print(f"   Phản biện    : {review.get('feedback')}")
          print("═" * 75)

          # 5. THỰC THI LỆNH
          action = proposal.get("action")
          if review.get("approved"):
            if action in ("OPEN_LONG", "OPEN_SHORT") and pos is None:
              side = "LONG" if action == "OPEN_LONG" else "SHORT"
              if self.paper_trader.open_position(
                  side, market_data["price"], cash_amount=70.0
              ):
                self.notifier.send(
                    f"🟢 **MỞ VỊ THẾ {side}** BTC/USDT @`{market_data['price']:,.2f}`"
                    " | Vốn: 70 USDT"
                )

            elif action == "CLOSE" and pos is not None:
              summary = self.paper_trader.close_position(
                  market_data["price"], exit_reason="AI_SIGNAL"
              )
              lesson = self.agent_team.reflector_agent.reflect(summary)
              self.recent_closed_trades.append(summary)
              print(f"💡 [BÀI HỌC VỪA RÚT RA]: {lesson}")
              self.notifier.send(
                  f"🔴 **ĐÓNG VỊ THẾ {summary['side']}** @"
                  f" `{market_data['price']:,.2f}` | PnL:"
                  f" `{summary['pnl_pct']:+.2f}%` ({summary['pnl_usdt']:+.4f}"
                  f" USDT)\n> 💡 *Bài học: {lesson}*"
              )

              # Đủ 3 lệnh thì Reflector tự tiến hóa bộ luật
              if len(self.recent_closed_trades) >= 3:
                self.agent_team.reflector_agent.auto_evolve_rules(
                    self.recent_closed_trades
                )

          self.save_active_position()

        time.sleep(15)

      except KeyboardInterrupt:
        print("\nĐã nhận lệnh dừng bot. Tạm biệt!")
        break
      except Exception as e:
        logging.error("Lỗi Exception ngoài vòng lặp: %s", e)
        self.agent_team.auditor_agent.inspect_error(str(e))
        time.sleep(20)


if __name__ == "__main__":
  main = Main()
  main.run()
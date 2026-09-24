"""Vòng lặp điều hành chính 6-Agent Crypto Scalping (BTC/USDT 5m)."""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
import requests

from agents.agent_team import AgentTeam, ReflectorAgent
from config.settings import Settings
from engine.paper_trader import PaperTrader
from notifiers.discord import DiscordNotifier

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
        self.last_1h_candle_time = None
        self.current_macro_directive = "FLEXIBLE"
        self.current_macro_bias = "SIDEWAY"
        self.current_macro_reason = "Khởi tạo hệ thống vĩ mô."
        self.recent_closed_trades = []

    def load_active_position(self):
        """Khôi phục vị thế khi bot khởi động lại."""
        self.paper_trader.load_active_position()

    def save_active_position(self):
        """Lưu vị thế hiện tại ra ổ cứng chống sập nguồn."""
        self.paper_trader.save_active_position()

    @staticmethod
    def _calc_ema(data: list, period: int) -> float:
        if not data or len(data) < period:
            return data[-1] if data else 0.0
        k = 2.0 / (period + 1)
        ema = [data[0]]
        for price in data[1:]:
            ema.append(price * k + ema[-1] * (1 - k))
        return ema[-1]

    @staticmethod
    def _calc_rsi(closes: list, period: int = 14) -> float:
        if len(closes) <= period:
            return 50.0
        gains, losses = [], []
        for i in range(1, period + 1):
            diff = closes[-i] - closes[-i - 1]
            if diff >= 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))
        avg_gain = sum(gains) / float(period)
        avg_loss = sum(losses) / float(period)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100.0 - (100.0 / (1.0 + rs)), 2)

    def fetch_market_data_5m(self) -> dict:
        """Lấy dữ liệu nến 5m từ Binance Public API."""
        url = f"https://api.binance.com/api/v3/klines?symbol={self.symbol}&interval=5m&limit=60"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                return {}
            klines = res.json()
            if not klines or len(klines) < 30:
                return {}

            closes = [float(k[4]) for k in klines]
            latest_candle = klines[-1]
            current_price = float(latest_candle[4])

            ema9 = self._calc_ema(closes, 9)
            ema21 = self._calc_ema(closes, 21)
            rsi14 = self._calc_rsi(closes, 14)

            if self.paper_trader.position:
                self.paper_trader.update_position(current_price)

            return {
                "open_time": latest_candle[0],
                "price": current_price,
                "rsi_14": rsi14,
                "ema_9": round(ema9, 2),
                "ema_21": round(ema21, 2),
                "macd": round(ema9 - ema21, 4),
                "capital": round(self.paper_trader.cash, 2),
                "available_cash": round(self.paper_trader.cash, 2),
                "total_equity": round(self.paper_trader.total_equity, 2),
            }
        except Exception as e:
            logging.warning("Lỗi fetch market data 5m: %s", e)
            return {}

    def fetch_market_data_1h(self) -> dict:
        """Lấy dữ liệu nến 1H từ Binance phục vụ StrategistAgent."""
        url = f"https://api.binance.com/api/v3/klines?symbol={self.symbol}&interval=1h&limit=250"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                return {}
            klines = res.json()
            if not klines or len(klines) < 200:
                return {}

            closes = [float(k[4]) for k in klines]
            latest_candle = klines[-1]

            return {
                "open_time": latest_candle[0],
                "price": float(latest_candle[4]),
                "rsi_14": self._calc_rsi(closes, 14),
                "ema_50": round(self._calc_ema(closes, 50), 2),
                "ema_200": round(self._calc_ema(closes, 200), 2),
            }
        except Exception as e:
            logging.warning("Lỗi fetch market data 1h: %s", e)
            return {}

    def update_macro_strategy(self, current_price: float, force_send: bool = False):
        """Cập nhật chỉ thị vĩ mô từ StrategistAgent và phát Embed lên Discord."""
        h1_data = self.fetch_market_data_1h()
        if not h1_data:
            return

        is_new_1h = self.last_1h_candle_time != h1_data["open_time"]
        if is_new_1h or force_send:
            self.last_1h_candle_time = h1_data["open_time"]
            macro_res = self.agent_team.strategist_agent.analyze_macro(
                symbol="BTC/USDT",
                current_price=current_price,
                h1_ind=h1_data
            )

            self.current_macro_directive = macro_res.get("directive", "FLEXIBLE")
            self.current_macro_bias = macro_res.get("macro_bias", "SIDEWAY")
            self.current_macro_reason = macro_res.get("reasoning", "Thị trường biến động hẹp.")

            # Bắn Card Embed Strategist 1H lên Discord kèm số dư quỹ
            self.notifier.send_strategist_update(
                directive=self.current_macro_directive,
                macro_bias=self.current_macro_bias,
                reasoning=self.current_macro_reason,
                total_equity=self.paper_trader.total_equity,
                available_cash=self.paper_trader.cash
            )
            logging.info(f"🧭 [STRATEGIST 1H] Phát chỉ thị mới: [{self.current_macro_directive}] | Quỹ: {self.paper_trader.total_equity:.2f} USDT")

    def print_dashboard(self, market_data: dict, sentiment: dict, rules: dict):
        """In bảng điều khiển trực quan theo từng nến."""
        pos = self.paper_trader.position
        pos_str = (
            f"{pos.side} @ {pos.entry_price:.2f} (PnL: {pos.pnl_pct:+.2f}%)"
            if pos
            else "TRỐNG"
        )

        total_eq = market_data.get("total_equity", self.paper_trader.total_equity)
        cash_avail = market_data.get("available_cash", self.paper_trader.cash)

        print("\n" + "═" * 75)
        print(
            f"📊 [{time.strftime('%H:%M:%S')}] BTC/USDT: {market_data.get('price', 0):,.2f} USDT"
            f" | Tổng tài sản: {total_eq:.2f} USDT (Khả dụng: {cash_avail:.2f} USDT)"
        )
        print(
            f"   Tin tức: [{sentiment.get('sentiment', 'NEUTRAL')} (Panic:"
            f" {sentiment.get('panic_score', 5)}/10)] | Bộ luật:"
            f" [v{rules.get('version', 1)}]"
        )
        print(f"   Chỉ thị 1H: [{self.current_macro_directive}] ({self.current_macro_bias})")
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
            f"🚀 **Bot 6-Agent Đã Khởi Động Thành Công!** Chế độ: `{mode}` | Vốn: `{self.paper_trader.total_equity:.2f} USDT`"
        )

        # ⚡ BẮN NGAY BẢN TIN VĨ MÔ STRATEGIST KHI VỪA BẬT BOT
        init_market = self.fetch_market_data_5m()
        if init_market:
            self.update_macro_strategy(init_market["price"], force_send=True)

        while True:
            try:
                market_data = self.fetch_market_data_5m()
                if not market_data:
                    time.sleep(10)
                    continue

                # Cập nhật chỉ đạo vĩ mô 1H (khi bước sang nến giờ mới)
                self.update_macro_strategy(market_data["price"], force_send=False)

                # Chỉ kích hoạt AI Team khi nến 5m mới mở cửa
                if market_data["open_time"] != self.last_candle_time:
                    self.last_candle_time = market_data["open_time"]

                    # 1. Thu thập tin tức & luật hiện hành
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

                    # 3. OPERATOR AGENT đề xuất (áp dụng chỉ thị 1H thực tế)
                    proposal = self.agent_team.operator_agent.analyze(
                        symbol="BTC/USDT",
                        current_price=market_data["price"],
                        indicators=market_data,
                        position_info=position_info,
                        macro_directive=self.current_macro_directive,
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
                        macro_directive=self.current_macro_directive,
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

                    # 5. THỰC THI LỆNH & GỬI DISCORD EMBED CHUẨN ĐỊNH DẠNG
                    action = proposal.get("action")
                    if review.get("approved"):
                        if action in ("OPEN_LONG", "OPEN_SHORT") and pos is None:
                            side = "LONG" if action == "OPEN_LONG" else "SHORT"
                            
                            # Phân bổ vốn: 70 USDT cho Trend (ONLY_LONG/SHORT), 30 USDT cho Sideway (FLEXIBLE)
                            trade_capital = 70.0 if self.current_macro_directive in ("ONLY_LONG", "ONLY_SHORT") else 30.0

                            if self.paper_trader.open_position(
                                side, market_data["price"], cash_amount=trade_capital
                            ):
                                # Gửi Card Embed mở vị thế chi tiết [AI TEAM]
                                self.notifier.send_trade_open(
                                    side=side,
                                    symbol="BTC/USDT",
                                    price=market_data["price"],
                                    capital=trade_capital,
                                    macro_directive=self.current_macro_directive,
                                    rules_version=rules.get("version", 13),
                                    operator_reason=proposal.get("reason", "N/A"),
                                    supervisor_reason=review.get("feedback", "N/A"),
                                    total_equity=self.paper_trader.total_equity,
                                    available_cash=self.paper_trader.cash
                                )

                        elif action == "CLOSE" and pos is not None:
                            exit_label = "AI_EARLY_EXIT_CLOSE" if pos.holding_candles < 12 else "AI_SIGNAL"
                            summary = self.paper_trader.close_position(
                                market_data["price"], exit_reason=exit_label
                            )
                            lesson = self.agent_team.reflector_agent.reflect(summary)
                            self.recent_closed_trades.append(summary)
                            print(f"💡 [BÀI HỌC VỪA RÚT RA]: {lesson}")

                            # Gửi Card Embed 🔔 [KẾT QUẢ GIAO DỊCH] chuẩn ảnh lịch sử
                            self.notifier.send_trade_close(
                                exit_type=summary.get("exit_reason", exit_label),
                                side=summary["side"],
                                symbol="BTC/USDT",
                                entry_price=summary["entry_price"],
                                exit_price=summary["exit_price"],
                                pnl_usdt=summary["pnl_usdt"],
                                pnl_pct=summary["pnl_pct"],
                                total_equity=summary.get("total_cash", self.paper_trader.total_equity),
                                cum_pnl_usdt=summary.get("cum_pnl_usdt", 0.0),
                                cum_pnl_pct=summary.get("cum_pnl_pct", 0.0),
                                reflector_lesson=lesson
                            )

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
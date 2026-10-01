"""Vòng lặp điều hành chính 6-Agent Crypto Scalping (BTC/USDT 5m)."""

# 1. Tắt toàn bộ cảnh báo của thư viện (đặc biệt là spam UserWarning joblib/sklearn trên Python 3.14)
import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import threading
import time
import requests

from agents.agent_team import AgentTeam, ReflectorAgent
from config.settings import Settings
from engine.paper_trader import PaperTrader
from engine.ml_retrainer import MLRetrainer
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

        # 5. Các biến quản lý trạng thái thị trường
        self.symbol = "BTCUSDT"
        self.last_candle_time = None
        self.last_1h_candle_time = None
        self.current_macro_directive = "FLEXIBLE"
        self.current_macro_bias = "SIDEWAY"
        self.current_macro_reason = "Khởi tạo hệ thống vĩ mô."
        self.recent_closed_trades = []

        # 6. Biến Cooldown chống FOMO sau Take Profit
        self.cooldown_until_candle = 0

        # 7. Bộ tự động Walk-Forward Retraining cho Machine Learning
        self.ml_retrainer = MLRetrainer(symbol="BTCUSDT", interval="5m", lookback_candles=3000)
        self.candle_counter = 0
        self.is_retraining = False

    def load_active_position(self):
        """Khôi phục vị thế khi bot khởi động lại."""
        self.paper_trader.load_active_position()

    def save_active_position(self):
        """Lưu vị thế hiện tại ra ổ cứng chống sập nguồn."""
        self.paper_trader.save_active_position()

    def _async_retrain_job(self):
        """Tiểu trình chạy ngầm: Tải 3,000 nến, huấn luyện Walk-Forward và Hot-Swap vào Operator."""
        try:
            self.is_retraining = True
            logging.info("🧵 [THREAD NGẦM] Bắt đầu tự động tái huấn luyện Walk-Forward...")
            result = self.ml_retrainer.retrain_model()
            if result.get("success"):
                self.agent_team.operator_agent.reload_model()
                self.notifier.send(
                    f"🧬 **[WALK-FORWARD RETRAINING] Tự Động Tái Huấn Luyện Thành Công!**\n"
                    f"• Dữ liệu học: `3,000 nến 5m mới nhất từ Binance`\n"
                    f"• OOS Accuracy: `{result['accuracy']}%` | OOS Precision: `{result['precision']}%` | F1: `{result.get('f1_score', 0)}%`\n"
                    f"• Trạng thái: Đã Hot-Swap nạp trực tiếp vào OperatorAgent."
                )
                logging.info(f"✅ [HOT-SWAP THÀNH CÔNG] Đã cập nhật mô hình mới vào OperatorAgent (OOS Acc: {result['accuracy']}%)")
            else:
                logging.warning(f"Tự động retrain thất bại: {result.get('reason')}")
        except Exception as e:
            logging.error(f"Lỗi trong tiểu trình retrain ngầm: {e}")
        finally:
            self.is_retraining = False

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
        """Lấy dữ liệu nến 5m từ Binance Public API và tính toán đầy đủ các features cho ML."""
        url = f"https://api.binance.com/api/v3/klines?symbol={self.symbol}&interval=5m&limit=60"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                return {}
            klines = res.json()
            if not klines or len(klines) < 35:
                return {}

            closes = [float(k[4]) for k in klines]
            volumes = [float(k[5]) for k in klines]
            current_price = closes[-1]

            ema9 = self._calc_ema(closes, 9)
            ema21 = self._calc_ema(closes, 21)
            rsi14 = self._calc_rsi(closes, 14)

            # Tính toán MACD & Signal Line (EMA9 của chuỗi MACD)
            macd_series = []
            for i in range(26, len(closes)):
                sub_c = closes[: i + 1]
                e12 = self._calc_ema(sub_c, 12)
                e26 = self._calc_ema(sub_c, 26)
                macd_series.append(e12 - e26)

            macd_val = macd_series[-1] if macd_series else (ema9 - ema21)
            macd_signal = self._calc_ema(macd_series, 9) if len(macd_series) >= 9 else 0.0

            # Tính biến động volume
            vol_change = ((volumes[-1] - volumes[-2]) / volumes[-2]) if len(volumes) >= 2 and volumes[-2] > 0 else 0.0

            return {
                "open_time": klines[-1][0],
                "price": current_price,
                "rsi_14": rsi14,
                "ema_9": round(ema9, 2),
                "ema_21": round(ema21, 2),
                "macd": round(macd_val, 4),
                "macd_signal": round(macd_signal, 4),
                "volume_change": round(vol_change, 4),
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

            self.notifier.send_strategist_update(
                directive=self.current_macro_directive,
                macro_bias=self.current_macro_bias,
                reasoning=self.current_macro_reason,
                total_equity=self.paper_trader.total_equity,
                available_cash=self.paper_trader.cash
            )
            logging.info(f"🧭 [STRATEGIST 1H] Phát chỉ thị mới: [{self.current_macro_directive}] | Quỹ: {self.paper_trader.total_equity:.2f} USDT")

    def _handle_close_position(self, exit_price: float, exit_reason: str):
        """Hàm chuẩn hóa quy trình đóng vị thế, thông báo và tự động tiến hóa."""
        summary = self.paper_trader.close_position(exit_price, exit_reason=exit_reason)
        if not summary:
            return

        # Kích hoạt Cooldown 2 nến (10 phút) nếu chốt lời để tránh FOMO đu đỉnh/đáy
        if "TP" in exit_reason or "TAKE_PROFIT" in exit_reason:
            self.cooldown_until_candle = self.candle_counter + 2
            logging.info("⏸️ [COOLDOWN] Kích hoạt nghỉ 2 nến sau Take Profit để hạ nhiệt thị trường.")

        # reflector.reflect() tự điều phối tiến hóa bộ luật khi thực sự cần thiết
        lesson = self.agent_team.reflector_agent.reflect(summary)
        self.recent_closed_trades.append(summary)
        print(f"💡 [BÀI HỌC VỪA RÚT RA]: {lesson}")

        self.notifier.send_trade_close(
            exit_type=summary.get("exit_reason", exit_reason),
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

        self.save_active_position()

    def print_dashboard(self, market_data: dict, sentiment: dict, rules: dict):
        """In bảng điều khiển trực quan theo từng nến."""
        pos = self.paper_trader.position
        pos_str = (
            f"{pos.side} @ {pos.entry_price:.2f} (PnL: {pos.pnl_pct:+.2f}%) [Nến: {pos.holding_candles}]"
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
            f"    Tin tức: [{sentiment.get('sentiment', 'NEUTRAL')} (Panic:"
            f" {sentiment.get('panic_score', 5)}/10)] | Bộ luật:"
            f" [v{rules.get('version', 1)}]"
        )
        print(f"    Chỉ thị 1H: [{self.current_macro_directive}] ({self.current_macro_bias})")
        print(f"    Vị thế: {pos_str}")
        print(
            f"    Chỉ báo 5m: RSI(14)={market_data.get('rsi_14')} |"
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

        init_market = self.fetch_market_data_5m()
        if init_market:
            self.update_macro_strategy(init_market["price"], force_send=True)

        while True:
            try:
                market_data = self.fetch_market_data_5m()
                if not market_data:
                    time.sleep(10)
                    continue

                current_price = market_data["price"]

                # Cập nhật chỉ đạo vĩ mô 1H khi sang nến giờ mới
                self.update_macro_strategy(current_price, force_send=False)

                # Chỉ kích hoạt logic phân tích khi nến 5m mới xuất hiện
                if market_data["open_time"] != self.last_candle_time:
                    self.last_candle_time = market_data["open_time"]
                    self.candle_counter += 1

                    # Cập nhật lãi/lỗ và số nến nắm giữ
                    if self.paper_trader.position:
                        self.paper_trader.update_position(current_price)

                    # Kích hoạt Walk-Forward Retraining ngầm mỗi 2,016 nến (7 ngày)
                    if self.candle_counter >= 2016 and not self.is_retraining:
                        self.candle_counter = 0
                        threading.Thread(target=self._async_retrain_job, daemon=True).start()

                    # 1. Thu thập dữ liệu tâm lý & bộ luật
                    sentiment_info = self.agent_team.sentiment_agent.analyze_market_sentiment()
                    rules = ReflectorAgent.load_rules()

                    # 2. In bảng điều khiển trực quan
                    self.print_dashboard(market_data, sentiment_info, rules)

                    # =========================================================================
                    # BƯỚC 1: KIỂM TRA THOÁT VỊ THẾ ĐỘC LẬP (0MS MECHANICAL & MACRO GUARD)
                    # =========================================================================
                    if self.paper_trader.position:
                        # 1.1 Kiểm tra các chốt chặn cơ học (Hard Stop, Trailing Stop, RSI TP >= +0.35%, Gãy EMA21)
                        should_mech_close, mech_reason = self.paper_trader.check_mechanical_exit(
                            current_price=current_price,
                            indicators=market_data
                        )
                        if should_mech_close:
                            logging.info(f"🚨 [CƠ HỌC TỰ ĐỘNG THOÁT VỊ THẾ]: {mech_reason}")
                            self._handle_close_position(current_price, exit_reason=mech_reason)
                            continue

                        # 1.2 Kiểm tra nếu Khung 1H đảo chiều ngược 100% với vị thế đang giữ
                        curr_side = self.paper_trader.position.side
                        if (curr_side == "LONG" and self.current_macro_directive == "ONLY_SHORT") or \
                           (curr_side == "SHORT" and self.current_macro_directive == "ONLY_LONG"):
                            macro_exit_reason = f"Đảo chiều xu hướng 1H sang [{self.current_macro_directive}]"
                            logging.info(f"🚨 [CƯỠNG CHẾ ĐÓNG VỊ THẾ NGHỊCH XU HƯỚNG 1H]: {macro_exit_reason}")
                            self._handle_close_position(current_price, exit_reason=macro_exit_reason)
                            continue

                    # =========================================================================
                    # BƯỚC 2: AI TEAM PHÂN TÍCH VÀ ĐỀ XUẤT HÀNH ĐỘNG
                    # =========================================================================
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

                    # Operator đề xuất
                    proposal = self.agent_team.operator_agent.analyze(
                        symbol="BTC/USDT",
                        current_price=current_price,
                        indicators=market_data,
                        position_info=position_info,
                        macro_directive=self.current_macro_directive,
                    )
                    conf_pct = int(proposal.get("confidence", 0.8) * 100)
                    action = proposal.get("action", "HOLD")
                    print(f"🤖 [OPERATOR]   : Đề xuất -> {action} (Độ tin cậy: {conf_pct}%)")
                    print(f"   Lập luận     : {proposal.get('reason')}")

                    # =========================================================================
                    # BƯỚC 3: XỬ LÝ LỆNH CLOSE TỪ AI OPERATOR (BẢO VỆ LỢI NHUẬN & CHẶN CHỐT NON)
                    # =========================================================================
                    if action == "CLOSE" and pos is not None:
                        ema21_val = market_data.get("ema_21", current_price)
                        # Kiểm tra xem cấu trúc kỹ thuật có thực sự bị phá vỡ không
                        is_structural_break = (pos.side == "LONG" and current_price < ema21_val) or \
                                              (pos.side == "SHORT" and current_price > ema21_val)

                        # Nếu đang có lãi nhưng quá mỏng (< 0.25%) và chưa bị gãy EMA21:
                        # CHẶN KHÔNG ĐÓNG để tránh bị phí sàn nuốt sạch lợi nhuận
                        if 0 < pos.pnl_pct < 0.25 and not is_structural_break:
                            logging.info(
                                f"🛡️ [CHẶN CHỐT NON]: PnL hiện tại ({pos.pnl_pct:+.2f}%) chưa đủ dày để bù phí sàn (yêu cầu >= +0.25%). "
                                f"Cấu trúc EMA21 vẫn an toàn. Tiếp tục giữ vị thế!"
                            )
                            continue

                        # Phân loại nhãn chính xác
                        if pos.pnl_pct >= 0.25:
                            exit_label = "AI_TAKE_PROFIT"
                        elif pos.holding_candles < 12:
                            exit_label = "AI_EARLY_EXIT_CLOSE"
                        else:
                            exit_label = "AI_TECHNICAL_CLOSE"

                        logging.info(f"🔔 [OPERATOR YÊU CẦU ĐÓNG VỊ THẾ]: {exit_label} | Lý do: {proposal.get('reason')}")
                        self._handle_close_position(current_price, exit_reason=exit_label)
                        continue

                    # =========================================================================
                    # BƯỚC 4: XỬ LÝ LẬT VỊ THẾ (REVERSE POSITION GUARD)
                    # =========================================================================
                    # Nếu đang giữ LONG mà Operator muốn OPEN_SHORT (hoặc ngược lại): Đóng lệnh cũ trước!
                    if pos is not None:
                        if (pos.side == "LONG" and action == "OPEN_SHORT") or \
                           (pos.side == "SHORT" and action == "OPEN_LONG"):
                            flip_reason = f"Lật vị thế theo tín hiệu {action}"
                            logging.info(f"🔄 [LẬT VỊ THẾ]: Đóng vị thế cũ {pos.side} trước khi xét mở mới!")
                            self._handle_close_position(current_price, exit_reason=flip_reason)
                            pos = None  # Đã giải phóng vị thế

                    # =========================================================================
                    # BƯỚC 5: SUPERVISOR KIỂM DUYỆT RỦI RO & MỞ VỊ THẾ MỚI (CHỈ KHI VÍ TRỐNG)
                    # =========================================================================
                    if pos is None and action in ("OPEN_LONG", "OPEN_SHORT"):
                        # Kiểm tra xem có đang trong thời gian Cooldown hạ nhiệt sau chốt lời hay không
                        if self.candle_counter < self.cooldown_until_candle:
                            remain_candles = self.cooldown_until_candle - self.candle_counter
                            print(f"🛡️  [COOLDOWN] Đang nghỉ hạ nhiệt sau Take Profit (còn {remain_candles} nến). Bỏ qua mở vị thế!")
                            print("═" * 75)
                        else:
                            past_lessons = ReflectorAgent.load_lessons(side=action.replace("OPEN_", ""))
                            review = self.agent_team.supervisor_agent.review(
                                proposal=proposal,
                                indicators=market_data,
                                cash=self.paper_trader.cash,
                                position_info={"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0},
                                macro_directive=self.current_macro_directive,
                                past_lessons=past_lessons,
                                sentiment_info=sentiment_info,
                            )
                            approved_icon = "✅ DUYỆT" if review.get("approved") else "❌ TỪ CHỐI"
                            print(f"🛡️  [SUPERVISOR] : Quyết định -> {approved_icon} (Mức rủi ro: {review.get('risk_score')}/10)")
                            print(f"   Phản biện    : {review.get('feedback')}")
                            print("═" * 75)

                            if review.get("approved"):
                                side = "LONG" if action == "OPEN_LONG" else "SHORT"
                                trade_capital = 70.0 if self.current_macro_directive in ("ONLY_LONG", "ONLY_SHORT") else 30.0

                                if self.paper_trader.open_position(side, current_price, cash_amount=trade_capital):
                                    self.notifier.send_trade_open(
                                        side=side,
                                        symbol="BTC/USDT",
                                        price=current_price,
                                        capital=trade_capital,
                                        macro_directive=self.current_macro_directive,
                                        rules_version=rules.get("version", 1),
                                        operator_reason=proposal.get("reason", "N/A"),
                                        supervisor_reason=review.get("feedback", "N/A"),
                                        total_equity=self.paper_trader.total_equity,
                                        available_cash=self.paper_trader.cash
                                    )
                    else:
                        print("🛡️  [SUPERVISOR] : Trạng thái -> DUY TRÌ VỊ THẾ / CHỜ ĐỢI TÍN HIỆU")
                        print("═" * 75)

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
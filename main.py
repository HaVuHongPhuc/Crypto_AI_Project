"""Main loop for the BTC/USDT 5m paper-trading system."""

from datetime import datetime
import json
import logging
import math
import os
from pathlib import Path
import sys
import time

import pandas as pd
import requests

from agents.agent_team import AgentTeam, ReflectorAgent
from config.settings import Settings
from data.preprocessor import add_indicators
from engine.paper_trader import PaperTrader
from engine.risk_manager import RiskManager
from notifiers.discord import DiscordNotifier

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "storage" / "bot.log"
RUNTIME_STATE_FILE = BASE_DIR / "storage" / "runtime_state.json"
INSTANCE_LOCK_FILE = BASE_DIR / "storage" / ".bot.lock"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
for _console_stream in (sys.stdout, sys.stderr):
    if hasattr(_console_stream, "reconfigure"):
        _console_stream.reconfigure(encoding="utf-8", errors="replace")
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
        self.config = Settings()
        self.symbol = self.config.symbol
        self.api_symbol = self.config.api_symbol
        self.timeframe = self.config.timeframe
        self.session = requests.Session()
        self.paper_trader = PaperTrader(initial_cash=self.config.initial_cash, fee_rate=self.config.fee_rate)
        self.agent_team = AgentTeam(self.config)
        self.notifier = DiscordNotifier(self.config.discord_webhook_url)
        self.risk_manager = RiskManager(
            position_size_pct=self.config.position_size_pct,
            stop_loss_pct=self.config.stop_loss_pct,
            take_profit_pct=self.config.take_profit_pct,
            trailing_stop_pct=self.config.trailing_stop_pct,
            trailing_activation_pct=self.config.trailing_activation_pct,
        )
        self.last_candle_time = self._load_runtime_cursor()
        self.recent_closed_trades = []
        self._lock_handle = None

    def _acquire_instance_lock(self) -> bool:
        INSTANCE_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        handle = INSTANCE_LOCK_FILE.open("a+", encoding="utf-8")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(" ")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._lock_handle = handle
        return True

    def _release_instance_lock(self):
        if not self._lock_handle:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._lock_handle.seek(0)
                msvcrt.locking(self._lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            logging.exception("Không giải phóng được instance lock")
        finally:
            self._lock_handle.close()
            self._lock_handle = None

    @staticmethod
    def _load_runtime_cursor():
        try:
            with RUNTIME_STATE_FILE.open("r", encoding="utf-8") as file:
                value = json.load(file).get("last_processed_candle")
                return int(value) if value is not None else None
        except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError):
            return None

    def _save_runtime_cursor(self, candle_time: int) -> bool:
        tmp_path = RUNTIME_STATE_FILE.with_suffix(".json.tmp")
        try:
            RUNTIME_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with tmp_path.open("w", encoding="utf-8") as file:
                json.dump({"last_processed_candle": int(candle_time)}, file)
                file.flush()
            tmp_path.replace(RUNTIME_STATE_FILE)
            return True
        except OSError:
            logging.exception("Không thể lưu thời điểm nến đã xử lý")
            return False

    def _fetch_klines(self, symbol: str, interval: str, limit: int) -> list:
        response = self.session.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=10,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise ValueError("Binance trả dữ liệu klines sai định dạng")
        return rows

    def fetch_current_price(self) -> float:
        response = self.session.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": self.api_symbol},
            timeout=10,
        )
        response.raise_for_status()
        price = float(response.json()["price"])
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Binance trả giá không hợp lệ")
        return price

    def fetch_market_data(self, current_price: float = None) -> dict:
        """Return indicators from closed candles and an optional live quote."""
        try:
            klines = self._fetch_klines(self.api_symbol, self.timeframe, self.config.candle_limit)
            # Binance includes the currently forming candle as the last row.
            closed = klines[:-1]
            if len(closed) < 30:
                return {}
            candles = pd.DataFrame(
                closed,
                columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"],
            )
            for column in ("open", "high", "low", "close", "volume"):
                candles[column] = pd.to_numeric(candles[column], errors="coerce")
            candles["timestamp"] = pd.to_numeric(candles["timestamp"], errors="coerce")
            candles = candles.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
            features = add_indicators(candles)
            if features.empty:
                return {}
            latest = features.iloc[-1]

            current_price = current_price if current_price is not None else self.fetch_current_price()
            if not math.isfinite(current_price) or current_price <= 0:
                return {}

            data = {column: float(latest[column]) for column in (
                "rsi_14", "macd", "macd_signal", "ema_9", "ema_21",
                "ema_spread_pct", "volume_change",
            )}
            data.update({
                "open_time": int(latest["timestamp"]),
                "price": current_price,
                "candle_close": float(latest["close"]),
                "candle_high": float(latest["high"]),
                "candle_low": float(latest["low"]),
                "capital": round(self.paper_trader.cash, 2),
            })
            return data
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
            logging.exception("Không lấy/tính được dữ liệu thị trường")
            return {}

    def fetch_macro_indicators(self) -> dict:
        """Build 1h trend inputs only from completed candles."""
        try:
            # Long startup history reduces EMA200 recursive/seed bias.
            klines = self._fetch_klines(self.api_symbol, "1h", 1000)
            closed = klines[:-1]
            if len(closed) < 800:
                return {}
            candles = pd.DataFrame(closed, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"])
            for column in ("open", "high", "low", "close", "volume"):
                candles[column] = pd.to_numeric(candles[column], errors="coerce")
            candles = candles.dropna(subset=["open", "high", "low", "close", "volume"])
            close = candles["close"]
            ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
            ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
            rsi = add_indicators(candles).iloc[-1]["rsi_14"]
            return {
                "close": float(close.iloc[-1]),
                "rsi_14": float(rsi),
                "ema_50": float(ema50),
                "ema_200": float(ema200),
            }
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
            logging.exception("Không lấy/tính được xu hướng 1H")
            return {}

    def print_dashboard(self, market_data: dict, sentiment: dict, rules: dict, macro: dict):
        pos = self.paper_trader.position
        pos_str = (
            f"{pos.side} @ {pos.entry_price:.2f} (PnL net: {pos.pnl_pct:+.2f}%)"
            if pos else "TRỐNG"
        )
        print("\n" + "═" * 75)
        print(f"📊 [{datetime.now().astimezone().strftime('%H:%M:%S')}] {self.symbol}: {market_data['price']:,.2f} USDT | Cash: {market_data['capital']:.2f} USDT")
        print(f"   Sentiment: {sentiment.get('sentiment', 'UNKNOWN')} (Panic: {sentiment.get('panic_score', 'N/A')}/10) | Rules v{rules.get('version', 1)} | Macro: {macro.get('directive', 'NO_TRADE')}")
        print(f"   Position: {pos_str}")
        print(f"   5m RSI={market_data['rsi_14']:.2f} | EMA9={market_data['ema_9']:.2f} | EMA21={market_data['ema_21']:.2f}")
        print("─" * 75)

    def _close_position(self, price: float, reason: str):
        summary = self.paper_trader.close_position(price, exit_reason=reason, symbol=self.symbol)
        if not summary:
            return
        self.recent_closed_trades.append(summary)
        lesson = f"Trade {summary['side']} closed by {reason}."
        try:
            lesson = self.agent_team.reflector_agent.reflect(summary)
        except Exception:
            logging.exception("Reflector không xử lý được trade đã đóng")
        self.notifier.send(
            f"🔴 Đóng {summary['side']} {self.symbol} @ {price:,.2f} | "
            f"PnL sau phí: {summary['pnl_pct']:+.2f}% ({summary['pnl_usdt']:+.4f} USDT)\n"
            f"Lý do: {reason} | Bài học: {lesson}"
        )
        if len(self.recent_closed_trades) >= 3:
            try:
                self.agent_team.reflector_agent.auto_evolve_rules(self.recent_closed_trades[-3:])
                self.recent_closed_trades.clear()
            except Exception:
                logging.exception("Không thể tiến hóa rules sau ba trade")

    def _entry_is_allowed(self, action: str, proposal: dict, indicators: dict, macro: dict, sentiment: dict) -> bool:
        """Repeat the hard entry invariants at the portfolio mutation boundary."""
        if self.paper_trader.position is not None or self.paper_trader.cash <= 0:
            return False
        try:
            confidence = float(proposal.get("confidence", 0))
            rsi = float(indicators["rsi_14"])
            ema9 = float(indicators["ema_9"])
            ema21 = float(indicators["ema_21"])
            panic = float(sentiment["panic_score"])
        except (KeyError, TypeError, ValueError):
            return False
        if not all(math.isfinite(value) for value in (confidence, rsi, ema9, ema21, panic)):
            return False
        if not 0.60 <= confidence <= 1.0 or sentiment.get("available") is not True or sentiment.get("error"):
            return False
        if panic >= 8 or not 1 <= panic <= 10 or sentiment.get("black_swan_alert") is not False:
            return False
        if sentiment.get("trading_advice") not in {"NORMAL", "CAUTION"}:
            return False
        directive = macro.get("directive")
        if directive not in {"ONLY_LONG", "ONLY_SHORT", "FLEXIBLE"}:
            return False
        if action == "OPEN_LONG":
            return directive != "ONLY_SHORT" and ema9 > ema21 and rsi > 50
        if action == "OPEN_SHORT":
            return directive != "ONLY_LONG" and ema9 < ema21 and rsi < 50
        return False

    @staticmethod
    def _has_strategy_exit(position, market_data: dict) -> bool:
        if not position:
            return False
        if position.side == "LONG":
            return market_data["candle_close"] < market_data["ema_21"] and market_data["rsi_14"] < 50
        if position.side == "SHORT":
            return market_data["candle_close"] > market_data["ema_21"] and market_data["rsi_14"] > 50
        return False

    def process_once(self) -> bool:
        """One safe loop iteration; returns False when market data is unavailable."""
        try:
            current_price = self.fetch_current_price()
        except (requests.RequestException, ValueError, KeyError, TypeError):
            logging.exception("Không lấy được giá hiện tại để quản lý rủi ro")
            return False

        position = self.paper_trader.position
        forced_exit = False
        if position:
            self.paper_trader.update_position(current_price)
            exit_reason = self.risk_manager.should_exit(position, current_price)
            if exit_reason:
                self._close_position(current_price, exit_reason)
                forced_exit = True

        market_data = self.fetch_market_data(current_price=current_price)
        if not market_data:
            return False
        candle_time = market_data["open_time"]
        if self.paper_trader.position:
            self.paper_trader.update_position(current_price, candle_time=candle_time)

        if candle_time == self.last_candle_time:
            return True

        self.last_candle_time = candle_time
        if forced_exit:
            self._save_runtime_cursor(candle_time)
            return True

        position = self.paper_trader.position
        if self._has_strategy_exit(position, market_data):
            self._close_position(market_data["price"], "EMA21_RSI_REVERSAL")
            self._save_runtime_cursor(candle_time)
            return True

        sentiment = self.agent_team.sentiment_agent.analyze_market_sentiment()
        macro_inputs = self.fetch_macro_indicators()
        macro = self.agent_team.strategist_agent.analyze_macro(
            self.symbol, macro_inputs.get("close", float("nan")), macro_inputs
        )
        rules = ReflectorAgent.load_rules()
        self.print_dashboard(market_data, sentiment, rules, macro)

        position = self.paper_trader.position
        position_info = (
            {
                "side": position.side,
                "entry_price": position.entry_price,
                "pnl_pct": position.pnl_pct,
                "pnl_usdt": position.pnl_usdt,
                "holding_candles": position.holding_candles,
            }
            if position else {"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0}
        )
        proposal = self.agent_team.operator_agent.analyze(
            symbol=self.symbol,
            current_price=market_data["candle_close"],
            indicators=market_data,
            position_info=position_info,
            macro_directive=macro.get("directive", "NO_TRADE"),
        )
        past_lessons = ReflectorAgent.load_lessons(side=position_info["side"])
        review = self.agent_team.supervisor_agent.review(
            proposal=proposal,
            indicators=market_data,
            cash=self.paper_trader.cash,
            position_info=position_info,
            macro_directive=macro.get("directive", "NO_TRADE"),
            past_lessons=past_lessons,
            sentiment_info=sentiment,
        )
        print(f"🤖 Operator: {proposal.get('action')} ({proposal.get('confidence', 0):.0%}) — {proposal.get('reason')}")
        print(f"🛡️ Supervisor: {'DUYỆT' if review.get('approved') else 'TỪ CHỐI'} — {review.get('feedback')}")

        # Persist the decision cursor before mutating the portfolio, preventing
        # a restart from replaying an already evaluated candle and duplicating it.
        if not self._save_runtime_cursor(candle_time):
            return True
        action = proposal.get("action")
        if (review.get("approved") and action in ("OPEN_LONG", "OPEN_SHORT")
                and self._entry_is_allowed(action, proposal, market_data, macro, sentiment)):
            stake = self.risk_manager.position_value(self.paper_trader.cash)
            side = "LONG" if action == "OPEN_LONG" else "SHORT"
            if self.paper_trader.open_position(side, market_data["price"], cash_amount=stake):
                self.notifier.send(f"🟢 Mở paper {side} {self.symbol} @ {market_data['price']:,.2f} | Stake: {stake:.2f} USDT")
        elif (review.get("approved") and action == "CLOSE"
              and self._has_strategy_exit(self.paper_trader.position, market_data)):
            self._close_position(market_data["price"], "AI_SIGNAL")

        self.paper_trader.save_active_position()
        self._save_runtime_cursor(candle_time)
        return True

    def run(self):
        if not self._acquire_instance_lock():
            raise RuntimeError("Bot paper đang chạy ở một process khác (storage/.bot.lock).")
        mode = self.config.llm_mode
        try:
            print(f"CRYPTO AI PAPER TRADER | {self.symbol} {self.timeframe} | LLM [{mode}]")
            self.notifier.send(f"Bot paper trading khởi động: {self.symbol} {self.timeframe} ({mode})")
            while True:
                try:
                    self.process_once()
                    time.sleep(self.config.loop_seconds)
                except KeyboardInterrupt:
                    print("Đã nhận lệnh dừng bot.")
                    break
                except Exception as exc:
                    logging.exception("Lỗi ngoài vòng lặp: %s", exc)
                    try:
                        diagnosis = self.agent_team.auditor_agent.inspect_error(str(exc))
                        logging.error("Auditor: %s", diagnosis)
                    except Exception:
                        logging.exception("Auditor không thể chẩn đoán lỗi")
                    time.sleep(max(self.config.loop_seconds, 10))
        finally:
            self._release_instance_lock()


if __name__ == "__main__":
    Main().run()

"""Paper trading ledger with durable cash, open position, and closed trades."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import csv
import json
import logging
import math
import os
from pathlib import Path
from typing import Optional
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent.parent
ACTIVE_POS_FILE = BASE_DIR / "storage" / "active_position.json"
TRADES_FILE = BASE_DIR / "storage" / "trades.csv"
TRADE_COLUMNS = [
    "symbol", "side", "entry_price", "exit_price", "amount", "pnl",
    "pnl_pct", "reason", "opened_at", "closed_at", "final_cash",
]


@dataclass
class ActivePosition:
    side: str
    entry_price: float
    amount: float
    entry_time: str
    pnl_pct: float = 0.0
    pnl_usdt: float = 0.0
    holding_candles: int = 0
    stake: float = 0.0
    entry_fee: float = 0.0
    extreme_price: float = 0.0
    last_candle_time: Optional[int] = None
    trade_id: str = ""


Position = ActivePosition


class PaperTrader:
    def __init__(self, initial_cash: float = 100.0, fee_rate: float = 0.0005):
        if not math.isfinite(initial_cash) or initial_cash < 0:
            raise ValueError("initial_cash phải là số hữu hạn không âm")
        if not math.isfinite(fee_rate) or not 0 <= fee_rate < 1:
            raise ValueError("fee_rate phải nằm trong [0, 1)")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.fee_rate = float(fee_rate)
        self.position: Optional[ActivePosition] = None
        self.load_active_position()

    def load_active_position(self):
        """Khôi phục ledger; vẫn đọc định dạng vị thế phẳng cũ."""
        if not ACTIVE_POS_FILE.exists():
            return
        try:
            with ACTIVE_POS_FILE.open("r", encoding="utf-8") as file:
                state = json.load(file)
            if not isinstance(state, dict):
                raise ValueError("Ledger cần là JSON object")
            if not state:
                raise ValueError("Ledger rỗng; từ chối khởi động để tránh reset paper account")

            if "position" in state or "schema_version" in state:
                cash = state.get("cash")
                if (not isinstance(cash, (int, float)) or isinstance(cash, bool)
                        or not math.isfinite(cash) or cash < 0):
                    raise ValueError("Ledger thiếu cash hợp lệ")
                self.cash = float(cash)
                position_data = state.get("position")
                if position_data is not None and not isinstance(position_data, dict):
                    raise ValueError("Ledger position cần là object hoặc null")
            else:
                # Legacy active_position.json held only the position fields.
                position_data = state
                if "side" in state and state.get("side") not in ("LONG", "SHORT"):
                    raise ValueError("Ledger có side không hợp lệ")

            if isinstance(position_data, dict):
                side = str(position_data.get("side", "")).upper()
                if side not in ("LONG", "SHORT"):
                    raise ValueError("Ledger có position nhưng thiếu side LONG/SHORT hợp lệ")
                allowed = ActivePosition.__dataclass_fields__
                cleaned = {key: value for key, value in position_data.items() if key in allowed}
                cleaned["side"] = side
                cleaned.setdefault("stake", float(cleaned.get("amount", 0)) * float(cleaned.get("entry_price", 0)))
                cleaned.setdefault("entry_fee", 0.0)
                cleaned.setdefault("extreme_price", float(cleaned.get("entry_price", 0)))
                cleaned.setdefault("pnl_pct", 0.0)
                cleaned.setdefault("pnl_usdt", 0.0)
                cleaned.setdefault("holding_candles", 0)
                cleaned.setdefault("entry_time", datetime.now(timezone.utc).isoformat())
                cleaned.setdefault("trade_id", uuid4().hex)

                for key in ("entry_price", "amount", "stake", "entry_fee", "extreme_price", "pnl_pct", "pnl_usdt"):
                    try:
                        cleaned[key] = float(cleaned[key])
                    except (TypeError, ValueError, KeyError) as exc:
                        raise ValueError(f"Ledger có {key} không hợp lệ") from exc
                    if not math.isfinite(cleaned[key]):
                        raise ValueError(f"Ledger có {key} không hữu hạn")
                if cleaned["stake"] <= 0:
                    cleaned["stake"] = cleaned["entry_price"] * cleaned["amount"]
                if cleaned["extreme_price"] <= 0:
                    cleaned["extreme_price"] = cleaned["entry_price"]
                if (cleaned["entry_price"] <= 0 or cleaned["amount"] <= 0 or cleaned["stake"] <= 0
                        or cleaned["entry_fee"] < 0 or cleaned["entry_fee"] > cleaned["stake"]
                        or cleaned["extreme_price"] <= 0):
                    raise ValueError("Ledger có vị thế sai giá, khối lượng, stake hoặc phí")
                try:
                    holding_candles = int(cleaned["holding_candles"])
                except (TypeError, ValueError) as exc:
                    raise ValueError("Ledger có holding_candles không hợp lệ") from exc
                if holding_candles < 0 or holding_candles != cleaned["holding_candles"]:
                    raise ValueError("Ledger có holding_candles không hợp lệ")
                cleaned["holding_candles"] = holding_candles
                if cleaned.get("last_candle_time") is not None:
                    try:
                        cleaned["last_candle_time"] = int(cleaned["last_candle_time"])
                    except (TypeError, ValueError) as exc:
                        raise ValueError("Ledger có last_candle_time không hợp lệ") from exc
                if not isinstance(cleaned.get("entry_time"), str):
                    raise ValueError("Ledger có entry_time không hợp lệ")
                if not isinstance(cleaned.get("trade_id"), str) or not cleaned["trade_id"]:
                    cleaned["trade_id"] = uuid4().hex
                self.position = ActivePosition(**cleaned)
                logging.info("Khôi phục vị thế %s @ %.8f", self.position.side, self.position.entry_price)
        except Exception as exc:
            logging.error("Không thể đọc ledger %s: %s", ACTIVE_POS_FILE, exc)
            raise RuntimeError("Không thể khởi động paper trader khi ledger không hợp lệ") from exc

    def save_active_position(self) -> bool:
        """Ghi ledger nguyên tử để cash và position luôn được lưu cùng nhau."""
        ACTIVE_POS_FILE.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "schema_version": 2,
            "cash": self.cash,
            "position": asdict(self.position) if self.position else None,
        }
        tmp_path = ACTIVE_POS_FILE.with_suffix(ACTIVE_POS_FILE.suffix + ".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as file:
                json.dump(state, file, ensure_ascii=False, indent=2, allow_nan=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp_path, ACTIVE_POS_FILE)
            return True
        except Exception as exc:
            logging.error("Lỗi lưu ledger %s: %s", ACTIVE_POS_FILE, exc)
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def open_position(self, side: str, price: float, cash_amount: float = 70.0) -> bool:
        side = str(side).upper()
        if side not in ("LONG", "SHORT"):
            raise ValueError("side phải là LONG hoặc SHORT")
        if not math.isfinite(price) or price <= 0:
            raise ValueError("price phải là số hữu hạn lớn hơn 0")
        if not math.isfinite(cash_amount) or cash_amount <= 0:
            raise ValueError("cash_amount phải là số hữu hạn lớn hơn 0")
        if self.position is not None:
            logging.warning("Đã có vị thế mở, không thể mở thêm")
            return False

        stake = min(float(cash_amount), self.cash)
        if stake <= 0:
            logging.warning("Không đủ cash để mở vị thế")
            return False
        entry_fee = stake * self.fee_rate
        amount = (stake - entry_fee) / price
        if amount <= 0:
            return False

        self.cash -= stake
        self.position = ActivePosition(
            side=side,
            entry_price=float(price),
            amount=amount,
            entry_time=datetime.now(timezone.utc).isoformat(),
            stake=stake,
            entry_fee=entry_fee,
            extreme_price=float(price),
            trade_id=uuid4().hex,
        )
        if not self.save_active_position():
            self.cash += stake
            self.position = None
            return False
        logging.info("Mở paper %s @ %.8f | stake %.4f | phí vào %.6f", side, price, stake, entry_fee)
        return True

    def update_position(self, current_price: float, candle_time: Optional[int] = None):
        if not self.position:
            return
        if not math.isfinite(current_price) or current_price <= 0:
            return

        position = self.position
        if position.side == "LONG":
            position.extreme_price = max(position.extreme_price, current_price)
            gross_pnl = (current_price - position.entry_price) * position.amount
        else:
            position.extreme_price = min(position.extreme_price or position.entry_price, current_price)
            gross_pnl = (position.entry_price - current_price) * position.amount
        estimated_exit_fee = current_price * position.amount * self.fee_rate
        position.pnl_usdt = gross_pnl - position.entry_fee - estimated_exit_fee
        denominator = position.stake or (position.entry_price * position.amount)
        position.pnl_pct = (position.pnl_usdt / denominator * 100) if denominator > 0 else 0.0

        if candle_time is not None and position.last_candle_time != candle_time:
            position.holding_candles += 1
            position.last_candle_time = candle_time
        self.save_active_position()

    def close_position(self, exit_price: float, exit_reason: str = "SIGNAL", symbol: str = "BTC/USDT") -> dict:
        if not self.position:
            return {}
        if not math.isfinite(exit_price) or exit_price <= 0:
            raise ValueError("exit_price phải là số hữu hạn lớn hơn 0")

        position = self.position
        exit_fee = position.amount * exit_price * self.fee_rate
        if position.side == "LONG":
            proceeds = position.amount * exit_price - exit_fee
            pnl_usdt = proceeds - (position.stake or position.entry_price * position.amount)
            cash_return = proceeds
        else:
            price_pnl = (position.entry_price - exit_price) * position.amount
            pnl_usdt = price_pnl - position.entry_fee - exit_fee
            cash_return = (position.stake or position.entry_price * position.amount) + pnl_usdt

        stake = position.stake or position.entry_price * position.amount
        pnl_pct = (pnl_usdt / stake * 100) if stake > 0 else 0.0
        self.cash += cash_return
        summary = {
            "trade_id": position.trade_id,
            "symbol": symbol,
            "side": position.side,
            "entry_price": position.entry_price,
            "exit_price": float(exit_price),
            "amount": position.amount,
            "stake": stake,
            "entry_fee": position.entry_fee,
            "exit_fee": exit_fee,
            "pnl_pct": pnl_pct,
            "pnl_usdt": pnl_usdt,
            "exit_reason": exit_reason,
            "holding_candles": position.holding_candles,
            "opened_at": position.entry_time,
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "final_cash": self.cash,
        }
        self.position = None
        if not self.save_active_position():
            self.position = position
            self.cash -= cash_return
            raise OSError("Không thể lưu ledger sau khi đóng vị thế")
        self._append_closed_trade(summary)
        logging.info("Đóng paper %s @ %.8f | PnL: %+.4f USDT (%+.3f%%)", summary["side"], exit_price, pnl_usdt, pnl_pct)
        return summary

    @staticmethod
    def _append_closed_trade(summary: dict):
        TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not TRADES_FILE.exists() or TRADES_FILE.stat().st_size == 0
        row = {
            "symbol": summary["symbol"], "side": summary["side"],
            "entry_price": summary["entry_price"], "exit_price": summary["exit_price"],
            "amount": summary["amount"], "pnl": summary["pnl_usdt"],
            "pnl_pct": summary["pnl_pct"], "reason": summary["exit_reason"],
            "opened_at": summary["opened_at"], "closed_at": summary["closed_at"],
            "final_cash": summary["final_cash"],
        }
        try:
            with TRADES_FILE.open("a", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=TRADE_COLUMNS)
                if needs_header:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as exc:
            logging.error("Không thể ghi trade history: %s", exc)

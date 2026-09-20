"""Paper trading engine supporting both LONG and SHORT positions with trailing-stop tracking."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import csv

TRADE_FIELDS = [
    "symbol",
    "side",
    "entry_price",
    "exit_price",
    "amount",
    "pnl",
    "pnl_pct",
    "reason",
    "opened_at",
    "closed_at",
    "final_cash",
]


@dataclass
class Position:
    symbol: str
    side: str  # "LONG" hoặc "SHORT"
    entry_price: float
    amount: float
    value: float
    opened_at: str
    extreme_price: float  # Đỉnh cao nhất (LONG) hoặc đáy thấp nhất (SHORT) kể từ lúc vào lệnh


class PaperTrader:
    def __init__(self, initial_cash: float = 10000.0, trades_path: str | Path = "storage/trades.csv") -> None:
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.position: Position | None = None
        self.trade_history: list[dict] = []
        self.trades_path = Path(trades_path)
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_trade_log_schema()

    def _ensure_trade_log_schema(self) -> None:
        # Move aside a legacy CSV so the new LONG/SHORT columns don't get misaligned.
        if not self.trades_path.exists() or self.trades_path.stat().st_size == 0:
            return
        with self.trades_path.open("r", encoding="utf-8") as file:
            header = file.readline().strip().split(",")
        if header != TRADE_FIELDS:
            self.trades_path.rename(self.trades_path.with_suffix(".legacy.csv"))

    def open_position(self, symbol: str, side: str, price: float, value: float) -> bool:
        if self.position is not None or value <= 0 or value > self.cash:
            return False

        amount = value / price
        self.cash -= value
        self.position = Position(
            symbol=symbol,
            side=side.upper(),
            entry_price=price,
            amount=amount,
            value=value,
            opened_at=self._now(),
            extreme_price=price,
        )
        return True

    def close_position(self, current_price: float, reason: str = "MANUAL") -> float:
        if not self.position:
            return 0.0

        pos = self.position
        if pos.side == "LONG":
            pnl = (current_price - pos.entry_price) * pos.amount
        else:  # SHORT: giá giảm thì lãi, giá tăng thì lỗ
            pnl = (pos.entry_price - current_price) * pos.amount

        self.cash += pos.value + pnl

        record = {
            "symbol": pos.symbol,
            "side": pos.side,
            "entry_price": pos.entry_price,
            "exit_price": current_price,
            "amount": pos.amount,
            "pnl": pnl,
            "pnl_pct": (pnl / pos.value) * 100 if pos.value else 0.0,
            "reason": reason,
            "opened_at": pos.opened_at,
            "closed_at": self._now(),
            "final_cash": self.cash,
        }
        self.trade_history.append(record)
        self._record(record)

        self.position = None
        return pnl

    def equity(self, current_price: float | None = None) -> float:
        if not self.position or current_price is None:
            return self.cash

        pos = self.position
        if pos.side == "LONG":
            unrealized_pnl = (current_price - pos.entry_price) * pos.amount
        else:
            unrealized_pnl = (pos.entry_price - current_price) * pos.amount

        return self.cash + pos.value + unrealized_pnl

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _record(self, record: dict) -> None:
        write_header = not self.trades_path.exists() or self.trades_path.stat().st_size == 0
        with self.trades_path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=TRADE_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(record)

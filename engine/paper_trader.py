"""PaperTrader: Quản lý vị thế giả lập, trừ phí thực tế và khôi phục khi sập nguồn."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
ACTIVE_POS_FILE = BASE_DIR / "storage" / "active_position.json"
WALLET_FILE = BASE_DIR / "storage" / "wallet.json"


@dataclass
class ActivePosition:
    side: str  # "LONG" hoặc "SHORT"
    entry_price: float
    amount: float
    entry_time: str
    pnl_pct: float = 0.0
    pnl_usdt: float = 0.0
    holding_candles: int = 0


# Tương thích ngược nếu code khác gọi tên Position
Position = ActivePosition


class PaperTrader:

    def __init__(self, initial_cash: float = 100.0, fee_rate: float = 0.0005):
        self.fee_rate = fee_rate  # 0.05% phí sàn mỗi chiều mở/đóng
        self.position: Optional[ActivePosition] = None
        
        # 1. Nạp vị thế đang chạy (nếu có)
        self.load_active_position()

        # 2. Khôi phục số dư ví thực tế và vốn khởi điểm
        self.initial_cash, self.cash = self.load_wallet(initial_cash)

    @property
    def total_equity(self) -> float:
        """Tổng tài sản thực tế = Tiền mặt khả dụng + Ký quỹ vị thế + PnL thả nổi."""
        if self.position:
            margin = self.position.amount * self.position.entry_price
            return self.cash + margin + self.position.pnl_usdt
        return self.cash

    def load_wallet(self, default_initial_cash: float) -> tuple[float, float]:
        """Khôi phục vốn gốc ban đầu và số dư tiền mặt thực tế từ file ổ cứng."""
        if WALLET_FILE.exists():
            try:
                with open(WALLET_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    init_cash = float(data.get("initial_cash", default_initial_cash))
                    curr_cash = float(data.get("cash", init_cash))
                    return init_cash, curr_cash
            except Exception:
                pass

        # Chưa có file wallet nhưng đang giữ vị thế
        if self.position:
            pos_cost = self.position.amount * self.position.entry_price
            return default_initial_cash, max(0.0, default_initial_cash - pos_cost)

        return default_initial_cash, default_initial_cash

    def save_wallet(self):
        """Lưu cả vốn ban đầu và số dư khả dụng ra ổ cứng."""
        WALLET_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(WALLET_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "initial_cash": round(self.initial_cash, 4),
                        "cash": round(self.cash, 4)
                    },
                    f,
                    ensure_ascii=False,
                    indent=2
                )
        except Exception as e:
            logging.error("Lỗi lưu wallet.json: %s", e)

    def load_active_position(self):
        """Khôi phục vị thế đang chạy khi bot bị khởi động lại hoặc mất điện."""
        if not ACTIVE_POS_FILE.exists():
            return
        try:
            with open(ACTIVE_POS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and data.get("side") in ("LONG", "SHORT"):
                self.position = ActivePosition(**data)
                logging.info(
                    ">>> [PHỤC HỒI VỊ THẾ] Đã nạp lại vị thế %s @ %s USDT",
                    self.position.side,
                    self.position.entry_price,
                )
        except Exception as e:
            logging.warning("Không thể đọc active_position.json: %s", e)

    def save_active_position(self):
        """Lưu trạng thái vị thế và số dư ví ra ổ cứng."""
        ACTIVE_POS_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(ACTIVE_POS_FILE, "w", encoding="utf-8") as f:
                if self.position:
                    json.dump(asdict(self.position), f, ensure_ascii=False, indent=2)
                else:
                    json.dump({}, f)
            self.save_wallet()
        except Exception as e:
            logging.error("Lỗi lưu active_position.json: %s", e)

    def open_position(
        self, side: str, price: float, cash_amount: float = 70.0
    ) -> bool:
        if self.position is not None:
            logging.warning("Đang có vị thế mở, không thể mở thêm!")
            return False

        if cash_amount > self.cash:
            cash_amount = self.cash

        if cash_amount <= 0:
            logging.warning("Không đủ số dư khả dụng để mở lệnh!")
            return False

        fee = cash_amount * self.fee_rate
        net_cash = cash_amount - fee
        amount = net_cash / price

        self.cash -= cash_amount
        self.position = ActivePosition(
            side=side,
            entry_price=price,
            amount=amount,
            entry_time=datetime.now(timezone.utc).isoformat(),
            pnl_pct=0.0,
            pnl_usdt=-fee,
            holding_candles=0,
        )
        self.save_active_position()
        logging.info(
            ">>> [PAPER TRADER] Mở %s @ %s | Vốn: %s USDT (Phí: -%s USDT) | Tiền mặt còn: %.2f USDT",
            side,
            price,
            cash_amount,
            fee,
            self.cash,
        )
        return True

    def update_position(self, current_price: float):
        if not self.position:
            return

        self.position.holding_candles += 1
        if self.position.side == "LONG":
            diff = current_price - self.position.entry_price
            self.position.pnl_pct = (diff / self.position.entry_price) * 100
            self.position.pnl_usdt = diff * self.position.amount
        elif self.position.side == "SHORT":
            diff = self.position.entry_price - current_price
            self.position.pnl_pct = (diff / self.position.entry_price) * 100
            self.position.pnl_usdt = diff * self.position.amount

        self.save_active_position()

    def close_position(
        self, exit_price: float, exit_reason: str = "SIGNAL"
    ) -> dict:
        if not self.position:
            return {}

        gross_value = self.position.amount * exit_price
        exit_fee = gross_value * self.fee_rate

        if self.position.side == "LONG":
            pnl_usdt = (
                exit_price - self.position.entry_price
            ) * self.position.amount - exit_fee
        else:
            pnl_usdt = (
                self.position.entry_price - exit_price
            ) * self.position.amount - exit_fee

        pnl_pct = (
            pnl_usdt / (self.position.amount * self.position.entry_price)
        ) * 100
        net_return = gross_value - exit_fee
        self.cash += net_return

        # Tính toán lãi/lỗ lũy kế so với vốn ban đầu (ví dụ: 100 USDT)
        cum_pnl_usdt = self.cash - self.initial_cash
        cum_pnl_pct = (cum_pnl_usdt / self.initial_cash) * 100.0

        summary = {
            "side": self.position.side,
            "entry_price": self.position.entry_price,
            "exit_price": exit_price,
            "pnl_pct": pnl_pct,
            "pnl_usdt": pnl_usdt,
            "exit_reason": exit_reason,
            "total_cash": self.cash,
            "cum_pnl_usdt": cum_pnl_usdt,
            "cum_pnl_pct": cum_pnl_pct,
            "holding_candles": self.position.holding_candles,
        }

        self.position = None
        self.save_active_position()
        logging.info(
            ">>> [PAPER TRADER] Đóng %s @ %s | PnL: %+.2f%% (%+.4f USDT) | Số dư ví mới: %.2f USDT",
            summary["side"],
            exit_price,
            pnl_pct,
            pnl_usdt,
            self.cash,
        )
        return summary
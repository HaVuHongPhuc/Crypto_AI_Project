"""PaperTrader: Quản lý vị thế giả lập, trừ phí thực tế, Trailing Stop và chốt chặn cơ học 0ms."""

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
    peak_price: float = 0.0  # Giá đỉnh/đáy phục vụ Trailing Stop


# Tương thích ngược nếu code khác gọi tên Position
Position = ActivePosition


class PaperTrader:

    def __init__(
        self,
        initial_cash: float = 100.0,
        fee_rate: float = 0.0005,
        stop_loss_pct: float = 0.012,        # Cắt lỗ cứng -1.2%
        take_profit_pct: float = 0.015,      # Chốt lời cứng +1.5%
        trailing_activation_pct: float = 0.004,  # Kích hoạt Trailing Stop khi lãi +0.4%
        trailing_stop_pct: float = 0.005,    # Biên trượt Trailing Stop 0.5%
        max_holding_candles: int = 36        # Thoát lệnh hòa vốn nếu ngâm quá 36 nến (3 tiếng)
    ):
        self.fee_rate = fee_rate
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_activation_pct = trailing_activation_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.max_holding_candles = max_holding_candles
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
                if "peak_price" not in data or data["peak_price"] == 0.0:
                    data["peak_price"] = data.get("entry_price", 0.0)
                self.position = ActivePosition(**data)
                logging.info(
                    ">>> [PHỤC HỒI VỊ THẾ] Đã nạp lại vị thế %s @ %s USDT (Giữ: %d nến)",
                    self.position.side,
                    self.position.entry_price,
                    self.position.holding_candles
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
            peak_price=price
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
        """Cập nhật lợi nhuận tức thời, số nến nắm giữ và đỉnh/đáy giá."""
        if not self.position:
            return

        self.position.holding_candles += 1
        
        # Cập nhật peak_price (Đỉnh cao nhất với LONG, Đáy thấp nhất với SHORT)
        if self.position.side == "LONG":
            diff = current_price - self.position.entry_price
            self.position.pnl_pct = (diff / self.position.entry_price) * 100
            self.position.pnl_usdt = diff * self.position.amount
            if current_price > self.position.peak_price:
                self.position.peak_price = current_price
        elif self.position.side == "SHORT":
            diff = self.position.entry_price - current_price
            self.position.pnl_pct = (diff / self.position.entry_price) * 100
            self.position.pnl_usdt = diff * self.position.amount
            if self.position.peak_price == 0.0 or current_price < self.position.peak_price:
                self.position.peak_price = current_price

        self.save_active_position()

    def check_mechanical_exit(self, current_price: float, indicators: dict) -> tuple[bool, str]:
        """Thực thi các chốt chặn cơ học 0ms không cần phụ thuộc LLM."""
        if not self.position:
            return False, ""

        entry_price = self.position.entry_price
        side = self.position.side
        pnl_pct_decimal = (current_price - entry_price) / entry_price if side == "LONG" else (entry_price - current_price) / entry_price
        
        rsi = indicators.get("rsi_14", 50.0)
        ema9 = indicators.get("ema_9", 0.0)
        ema21 = indicators.get("ema_21", 0.0)

        # 1. Cắt lỗ cứng tuyệt đối (Hard Stop-Loss: -1.2%)
        if pnl_pct_decimal <= -self.stop_loss_pct:
            return True, f"Hard Stop-Loss hit ({pnl_pct_decimal * 100:.2f}%)"

        # 2. Chốt lời cứng mục tiêu (Hard Take-Profit: +1.5%)
        if pnl_pct_decimal >= self.take_profit_pct:
            return True, f"Hard Take-Profit hit ({pnl_pct_decimal * 100:.2f}%)"

        # 3. Trailing Stop: Đạt lãi tối thiểu +0.4%, đóng lệnh nếu giá thoái lui 0.5% từ đỉnh
        if side == "LONG":
            peak_pnl_pct = (self.position.peak_price - entry_price) / entry_price
            if peak_pnl_pct >= self.trailing_activation_pct:
                drawdown_from_peak = (self.position.peak_price - current_price) / self.position.peak_price
                if drawdown_from_peak >= self.trailing_stop_pct:
                    return True, f"Trailing Stop hit (Đỉnh: {self.position.peak_price:.2f}, Lãi còn: {pnl_pct_decimal * 100:.2f}%)"
        elif side == "SHORT":
            peak_pnl_pct = (entry_price - self.position.peak_price) / entry_price
            if peak_pnl_pct >= self.trailing_activation_pct:
                drawdown_from_peak = (current_price - self.position.peak_price) / self.position.peak_price
                if drawdown_from_peak >= self.trailing_stop_pct:
                    return True, f"Trailing Stop hit (Đáy: {self.position.peak_price:.2f}, Lãi còn: {pnl_pct_decimal * 100:.2f}%)"

        # 4. Chốt lời kỹ thuật theo RSI: BẮT BUỘC lãi tối thiểu >= +0.35% mới cho chốt để trừ sạch phí sàn
        if side == "LONG" and rsi >= 70.0 and pnl_pct_decimal >= 0.0035:
            return True, f"Technical TP: RSI Overbought ({rsi:.1f}) & PnL ({pnl_pct_decimal * 100:.2f}%)"
        if side == "SHORT" and rsi <= 30.0 and pnl_pct_decimal >= 0.0035:
            return True, f"Technical TP: RSI Oversold ({rsi:.1f}) & PnL ({pnl_pct_decimal * 100:.2f}%)"

        # 5. Cắt lỗ kỹ thuật: Giá đóng nến xuyên thủng EMA21 và EMA giao cắt ngược
        if side == "LONG" and current_price < ema21 and ema9 < ema21:
            return True, f"Technical Stop: Nến gãy dưới EMA21 ({current_price:.2f} < {ema21:.2f})"
        if side == "SHORT" and current_price > ema21 and ema9 > ema21:
            return True, f"Technical Stop: Nến phá lên trên EMA21 ({current_price:.2f} > {ema21:.2f})"

        # 6. Chốt chặn thời gian (Time-based Exit): Giữ quá 36 nến (~3 tiếng) mà thị trường đi ngang
        if self.position.holding_candles >= self.max_holding_candles:
            if abs(pnl_pct_decimal) < 0.003:  # Lợi nhuận lình xình quanh mức hòa vốn (+-0.3%)
                return True, f"Time-based Exit: Ngâm vốn {self.position.holding_candles} nến không bứt phá"

        return False, ""

    def close_position(
        self, exit_price: float, exit_reason: str = "SIGNAL"
    ) -> dict:
        """Đóng vị thế và tính toán hoàn tiền ví chính xác tuyệt đối cho cả LONG và SHORT."""
        if not self.position:
            return {}

        margin = self.position.amount * self.position.entry_price
        gross_value = self.position.amount * exit_price
        exit_fee = gross_value * self.fee_rate

        if self.position.side == "LONG":
            pnl_usdt = (exit_price - self.position.entry_price) * self.position.amount - exit_fee
        else:
            pnl_usdt = (self.position.entry_price - exit_price) * self.position.amount - exit_fee

        pnl_pct = (pnl_usdt / margin) * 100

        # [ĐÃ SỬA CHUẨN]: Hoàn vốn gốc ký quỹ + PnL lãi/lỗ thực tế về ví tiền mặt
        net_return = margin + pnl_usdt
        self.cash += net_return

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
            ">>> [PAPER TRADER] Đóng %s @ %s | Lý do: %s | PnL: %+.2f%% (%+.4f USDT) | Số dư ví mới: %.2f USDT",
            summary["side"],
            exit_price,
            exit_reason,
            pnl_pct,
            pnl_usdt,
            self.cash,
        )
        return summary
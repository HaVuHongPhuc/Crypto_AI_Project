"""Position sizing, fixed Stop-loss/Take-profit, and dynamic Trailing Stop for LONG & SHORT."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskManager:
    position_size_pct: float = 0.1
    stop_loss_pct: float = 0.01
    take_profit_pct: float | None = 0.03
    trailing_stop_pct: float = 0.008
    trailing_activation_pct: float = 0.01

    def position_value(self, cash: float) -> float:
        return max(0.0, cash * self.position_size_pct)

    def should_exit(self, position, current_price: float) -> str | None:
        if not position:
            return None

        entry = position.entry_price
        side = position.side

        if side == "LONG":
            if current_price > position.extreme_price:
                position.extreme_price = current_price
            peak = position.extreme_price
            max_gain_pct = (peak - entry) / entry

            if max_gain_pct >= self.trailing_activation_pct:
                trailing_stop_price = peak * (1.0 - self.trailing_stop_pct)
                if current_price <= trailing_stop_price:
                    return f"TRAILING_STOP_LONG (Đỉnh: {peak:.2f} -> Bán: {current_price:.2f})"

            if current_price <= entry * (1.0 - self.stop_loss_pct):
                return "STOP_LOSS_LONG"
            if self.take_profit_pct and current_price >= entry * (1.0 + self.take_profit_pct):
                return "TAKE_PROFIT_LONG"

        elif side == "SHORT":
            if current_price < position.extreme_price:
                position.extreme_price = current_price
            trough = position.extreme_price
            max_gain_pct = (entry - trough) / entry

            if max_gain_pct >= self.trailing_activation_pct:
                trailing_stop_price = trough * (1.0 + self.trailing_stop_pct)
                if current_price >= trailing_stop_price:
                    return f"TRAILING_STOP_SHORT (Đáy: {trough:.2f} -> Mua đóng: {current_price:.2f})"

            if current_price >= entry * (1.0 + self.stop_loss_pct):
                return "STOP_LOSS_SHORT"
            if self.take_profit_pct and current_price <= entry * (1.0 - self.take_profit_pct):
                return "TAKE_PROFIT_SHORT"

        return None

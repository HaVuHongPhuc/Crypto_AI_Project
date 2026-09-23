"""Position sizing, fixed Stop-loss/Take-profit, and dynamic Trailing Stop for LONG & SHORT."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class RiskManager:
  position_size_pct: float = 0.1
  stop_loss_pct: float = 0.01
  take_profit_pct: float | None = 0.03
  trailing_stop_pct: float = 0.008
  trailing_activation_pct: float = 0.01

  def position_value(self, cash: float) -> float:
    return max(0.0, cash * self.position_size_pct)

  def should_exit(
      self,
      position: Any = None,
      current_price: float = 0.0,
      *args,
      entry_price: Optional[float] = None,
      highest_price: Optional[float] = None,
      side: Optional[str] = None,
      **kwargs,
  ) -> str | None:
    """Kiểm tra điều kiện thoát lệnh: Stop-loss, Take-profit, Trailing Stop.

    Hỗ trợ cả:
    1. Gọi chuẩn: should_exit(position, current_price)
    2. Gọi test rời: should_exit(side="LONG", entry_price=...,
    current_price=..., highest_price=...)
    """
    if position is None and entry_price is None:
      return None

    # Tự động trích xuất thuộc tính dù truyền object, dict hay kwargs
    if hasattr(position, "entry_price"):
      entry = position.entry_price
      pos_side = position.side
      extreme = getattr(position, "extreme_price", entry)
      is_obj = True
    elif isinstance(position, dict):
      entry = position.get("entry_price", entry_price or 0.0)
      pos_side = position.get("side", side or "LONG")
      extreme = position.get("extreme_price", highest_price or entry)
      is_obj = False
    else:
      entry = entry_price if entry_price is not None else 0.0
      pos_side = side or (position if isinstance(position, str) else "LONG")
      extreme = highest_price if highest_price is not None else entry
      is_obj = False

    if entry <= 0 or current_price <= 0:
      return None

    pos_side = pos_side.upper()

    # ------------------------------------------------------------------
    # 1. QUẢN TRỊ VỊ THẾ LONG
    # ------------------------------------------------------------------
    if pos_side == "LONG":
      if current_price > extreme:
        extreme = current_price
        if is_obj:
          position.extreme_price = current_price
      peak = extreme
      max_gain_pct = (peak - entry) / entry

      # Trailing Stop kích hoạt khi lãi >= 1% và giá rớt 0.8% từ đỉnh
      if max_gain_pct >= self.trailing_activation_pct:
        trailing_stop_price = peak * (1.0 - self.trailing_stop_pct)
        if current_price <= trailing_stop_price:
          return (
              f"TRAILING_STOP_LONG (Đỉnh: {peak:.2f} -> Bán:"
              f" {current_price:.2f})"
          )

      # Cắt lỗ cứng (1%)
      if current_price <= entry * (1.0 - self.stop_loss_pct):
        return "STOP_LOSS_LONG"

      # Chốt lời cứng (3%)
      if self.take_profit_pct and current_price >= entry * (
          1.0 + self.take_profit_pct
      ):
        return "TAKE_PROFIT_LONG"

    # ------------------------------------------------------------------
    # 2. QUẢN TRỊ VỊ THẾ SHORT
    # ------------------------------------------------------------------
    elif pos_side == "SHORT":
      if current_price < extreme:
        extreme = current_price
        if is_obj:
          position.extreme_price = current_price
      trough = extreme
      max_gain_pct = (entry - trough) / entry

      # Trailing Stop kích hoạt khi lãi >= 1% và giá tăng 0.8% từ đáy
      if max_gain_pct >= self.trailing_activation_pct:
        trailing_stop_price = trough * (1.0 + self.trailing_stop_pct)
        if current_price >= trailing_stop_price:
          return (
              f"TRAILING_STOP_SHORT (Đáy: {trough:.2f} -> Mua đóng:"
              f" {current_price:.2f})"
          )

      # Cắt lỗ cứng (1%)
      if current_price >= entry * (1.0 + self.stop_loss_pct):
        return "STOP_LOSS_SHORT"

      # Chốt lời cứng (3%)
      if self.take_profit_pct and current_price <= entry * (
          1.0 - self.take_profit_pct
      ):
        return "TAKE_PROFIT_SHORT"

    return None
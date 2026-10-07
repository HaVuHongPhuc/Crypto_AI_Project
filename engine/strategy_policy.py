"""Deterministic strategy thresholds shared by agents and execution gates."""

import math


MACRO_LONG_RSI_MIN = 52.0
MACRO_SHORT_RSI_MAX = 48.0
ENTRY_LONG_RSI_MIN = 50.0
ENTRY_SHORT_RSI_MAX = 50.0
MIN_ENTRY_CONFIDENCE = 0.60
MAX_ENTRY_PANIC_SCORE = 8.0


def entry_signal_rejection(action: str, macro_directive: str, indicators: dict) -> str | None:
    """Return why a proposed entry violates the executable technical policy."""
    action = str(action).upper()
    if action not in {"OPEN_LONG", "OPEN_SHORT"}:
        return "action không phải OPEN_LONG/OPEN_SHORT"
    if not isinstance(macro_directive, str):
        return "macro directive sai kiểu dữ liệu"
    if macro_directive not in {"ONLY_LONG", "ONLY_SHORT", "FLEXIBLE"}:
        return "macro directive không hợp lệ/NO_TRADE"
    if action == "OPEN_LONG" and macro_directive == "ONLY_SHORT":
        return "macro ONLY_SHORT chặn LONG"
    if action == "OPEN_SHORT" and macro_directive == "ONLY_LONG":
        return "macro ONLY_LONG chặn SHORT"

    try:
        raw_values = [indicators[name] for name in ("rsi_14", "ema_9", "ema_21")]
        if any(isinstance(value, bool) for value in raw_values):
            raise ValueError("boolean technical value")
        rsi, ema9, ema21 = (float(value) for value in raw_values)
    except (KeyError, TypeError, ValueError):
        return "thiếu RSI/EMA hợp lệ"
    if not all(math.isfinite(value) for value in (rsi, ema9, ema21)):
        return "RSI/EMA không hữu hạn"

    if action == "OPEN_LONG" and not (ema9 > ema21 and rsi > ENTRY_LONG_RSI_MIN):
        return f"LONG cần EMA9 > EMA21 và RSI > {ENTRY_LONG_RSI_MIN:g}"
    if action == "OPEN_SHORT" and not (ema9 < ema21 and rsi < ENTRY_SHORT_RSI_MAX):
        return f"SHORT cần EMA9 < EMA21 và RSI < {ENTRY_SHORT_RSI_MAX:g}"
    return None

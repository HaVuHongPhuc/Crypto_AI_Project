"""Technical indicators and model features."""

import pandas as pd

FEATURE_COLUMNS = [
    "rsi_14",
    "macd",
    "macd_signal",
    "ema_9",
    "ema_21",
    "ema_spread_pct",
    "volume_change",
]


def add_indicators(candles: pd.DataFrame) -> pd.DataFrame:
    data = candles.copy()
    delta = data["close"].diff()
    gains = delta.clip(lower=0).rolling(14).mean()
    losses = (-delta.clip(upper=0)).rolling(14).mean()
    relative_strength = gains / losses.replace(0, float("nan"))
    data["rsi_14"] = 100 - (100 / (1 + relative_strength))
    data.loc[(losses == 0) & (gains > 0), "rsi_14"] = 100
    data.loc[(losses == 0) & (gains == 0), "rsi_14"] = 50

    fast_ema = data["close"].ewm(span=12, adjust=False).mean()
    slow_ema = data["close"].ewm(span=26, adjust=False).mean()
    data["macd"] = fast_ema - slow_ema
    data["macd_signal"] = data["macd"].ewm(span=9, adjust=False).mean()
    data["ema_9"] = data["close"].ewm(span=9, adjust=False).mean()
    data["ema_21"] = data["close"].ewm(span=21, adjust=False).mean()
    data["ema_spread_pct"] = (data["ema_9"] - data["ema_21"]) / data["ema_21"]
    average_volume = data["volume"].rolling(20).mean()
    data["volume_change"] = data["volume"] / average_volume - 1
    return data.dropna()


def create_buy_labels(
    candles: pd.DataFrame,
    horizon: int = 5,
    take_profit_pct: float = 0.015,
    stop_loss_pct: float = 0.01,
) -> pd.Series:
    """Label BUY when take-profit is reached before stop-loss in future candles."""
    labels = pd.Series("HOLD", index=candles.index, dtype="object")
    highs = candles["high"].to_numpy()
    lows = candles["low"].to_numpy()
    closes = candles["close"].to_numpy()

    for index in range(len(candles) - horizon):
        take_profit = closes[index] * (1 + take_profit_pct)
        stop_loss = closes[index] * (1 - stop_loss_pct)
        for future_index in range(index + 1, index + horizon + 1):
            hit_profit = highs[future_index] >= take_profit
            hit_loss = lows[future_index] <= stop_loss
            if hit_loss:
                break
            if hit_profit:
                labels.iloc[index] = "BUY"
                break

    labels.iloc[-horizon:] = pd.NA
    return labels


class Preprocessor:
    """Wrapper class phục vụ Controller main.py và kịch bản test luồng."""

    FEATURE_COLUMNS = FEATURE_COLUMNS

    def __init__(self):
        pass

    def add_indicators(self, candles: pd.DataFrame) -> pd.DataFrame:
        return add_indicators(candles)

    def create_buy_labels(
        self,
        candles: pd.DataFrame,
        horizon: int = 5,
        take_profit_pct: float = 0.015,
        stop_loss_pct: float = 0.01,
    ) -> pd.Series:
        return create_buy_labels(candles, horizon, take_profit_pct, stop_loss_pct)


# Tương thích ngược nếu code khác gọi tên DataPreprocessor
DataPreprocessor = Preprocessor
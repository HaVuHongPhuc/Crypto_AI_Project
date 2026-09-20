"""Fetch OHLCV candles through CCXT, with pagination for large historical pulls."""

import time

import ccxt
import pandas as pd


class MarketDataFetcher:
    def __init__(self, exchange_id: str = "binance") -> None:
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({"enableRateLimit": True})

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
        rows = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        # Giữ "timestamp" (epoch ms) là cột dữ liệu, không set làm index, để callers (vd. main.py) đọc trực tiếp.
        frame["datetime"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        return frame

    def fetch_historical_ohlcv(self, symbol: str, timeframe: str, total_candles: int = 3000) -> pd.DataFrame:
        """Kéo nến lịch sử vượt giới hạn 1,000 nến/lần bằng cơ chế phân trang theo `since`."""
        timeframe_ms = self.exchange.parse_timeframe(timeframe) * 1000
        since = self.exchange.milliseconds() - (total_candles * timeframe_ms)

        all_ohlcv: list[list[float]] = []
        print(f"Đang thu thập {total_candles} nến {timeframe} cho cặp {symbol}...")

        while len(all_ohlcv) < total_candles:
            fetch_limit = min(1000, total_candles - len(all_ohlcv))
            candles = self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=fetch_limit)
            if not candles:
                break

            all_ohlcv.extend(candles)
            since = candles[-1][0] + timeframe_ms  # dời mốc since ngay sau nến cuối vừa nhận
            print(f"-> Đã tải: {len(all_ohlcv)}/{total_candles} nến...")
            time.sleep(self.exchange.rateLimit / 1000)

        frame = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        frame["datetime"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        frame = frame.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        # Loại bỏ nến cuối cùng vì có thể chưa đóng, dễ làm sai lệch chỉ báo (data leakage)
        return frame.iloc[:-1].reset_index(drop=True)


"""Script tải dữ liệu lịch sử quy mô lớn (35,000 nến) và lưu cố định ra file CSV."""

import os
import time

import ccxt
import pandas as pd


def fetch_and_save(
    symbol: str = "BTC/USDT",
    timeframe: str = "5m",
    total_candles: int = 35000,
    output_path: str = "storage/btc_5m.csv",
) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    exchange = ccxt.binance({
        "enableRateLimit": True,
        "timeout": 30000,
    })

    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000
    now_ms = exchange.milliseconds()
    since = now_ms - (total_candles * timeframe_ms)

    print("=" * 65)
    print(f" BẮT ĐẦU TẢI DATASET: {symbol} [{timeframe}]")
    print(f" Mục tiêu: {total_candles:,} nến (~{total_candles * 15 / 1440:.1f} ngày)")
    print(f" File lưu: {output_path}")
    print("=" * 65)

    all_ohlcv = []
    batch_count = 0

    while len(all_ohlcv) < total_candles:
        remaining = total_candles - len(all_ohlcv)
        fetch_limit = min(1000, remaining)

        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=fetch_limit)
            if not candles:
                print(" Không còn dữ liệu cũ hơn từ sàn.")
                break

            all_ohlcv.extend(candles)
            batch_count += 1

            last_ts = candles[-1][0]
            since = last_ts + timeframe_ms

            progress = (len(all_ohlcv) / total_candles) * 100
            current_date = pd.to_datetime(last_ts, unit="ms").strftime("%Y-%m-%d %H:%M")
            print(f"Batch {batch_count:02d}: Đã tải {len(all_ohlcv):,}/{total_candles:,} nến ({progress:5.1f}%) -> Nến tới ngày: {current_date}")

            if since >= now_ms:
                break

            time.sleep(exchange.rateLimit / 1000)

        except Exception as e:
            print(f" Lỗi mạng: {e}. Thử lại sau 3 giây...")
            time.sleep(3)

    df = pd.DataFrame(
        all_ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )

    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # Bỏ cây nến cuối cùng vì có thể chưa đóng, dễ làm sai lệch chỉ báo
    if len(df) > 0:
        df = df.iloc[:-1].reset_index(drop=True)

    df.to_csv(output_path, index=False)

    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print("=" * 65)
    print(" TẢI HOÀN TẤT VÀ ĐÃ LƯU THÀNH CÔNG!")
    print(f" Tổng số nến chuẩn: {len(df):,} nến")
    print(f" Khoảng thời gian : {df['datetime'].iloc[0]}  --->  {df['datetime'].iloc[-1]}")
    print(f" Dung lượng file   : {file_size_mb:.2f} MB")
    print("=" * 65)


if __name__ == "__main__":
    fetch_and_save()

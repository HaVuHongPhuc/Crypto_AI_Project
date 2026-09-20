"""Script độc lập thống kê hiệu suất giao dịch từ storage/trades.csv."""

import os
import pandas as pd
from config.settings import settings


def print_summary() -> None:
    csv_path = "storage/trades.csv"

    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        print("\n" + "═" * 70)
        print(" ⚠️  CHƯA CÓ LỆNH NÀO ĐƯỢC ĐÓNG HOÀN TẤT")
        print("═" * 70)
        print(" - Bot hiện đang giữ lệnh hoặc chưa có giao dịch nào chốt sổ.")
        print(f" - Vốn ban đầu cấu hình: {settings.initial_cash:,.2f} USDT")
        print(" - Vui lòng chờ lệnh hiện tại chạm TP/SL/Trailing Stop để cập nhật.")
        print("═" * 70 + "\n")
        return

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"❌ Lỗi khi đọc file dữ liệu {csv_path}: {e}")
        return

    if df.empty:
        print("\n[!] File storage/trades.csv rỗng.\n")
        return

    # Tính toán các chỉ số cốt lõi
    total_trades = len(df)
    wins = df[df["pnl"] > 0]
    losses = df[df["pnl"] < 0]
    evens = df[df["pnl"] == 0]

    win_count = len(wins)
    loss_count = len(losses)
    even_count = len(evens)
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0.0

    total_pnl = float(df["pnl"].sum())
    initial_cash = float(settings.initial_cash)
    current_cash = float(df["final_cash"].iloc[-1]) if "final_cash" in df.columns else (initial_cash + total_pnl)
    roi_pct = ((current_cash - initial_cash) / initial_cash) * 100
    sign = "+" if total_pnl >= 0 else ""

    # Thống kê phân loại theo chiều LONG / SHORT
    long_trades = df[df["side"] == "LONG"] if "side" in df.columns else pd.DataFrame()
    short_trades = df[df["side"] == "SHORT"] if "side" in df.columns else pd.DataFrame()

    print("\n" + "═" * 72)
    print("          📊 BÁO CÁO THỐNG KÊ TỔNG THỂ TÀI KHOẢN (PORTFOLIO)")
    print("═" * 72)
    print(f" 💰 Vốn khởi điểm ban đầu   : {initial_cash:,.2f} USDT")
    print(f" 💵 Tổng số tiền hiện có    : {current_cash:,.2f} USDT")
    print(f" 📈 Tổng Lời / Lỗ tích lũy  : {sign}{total_pnl:,.2f} USDT ({sign}{roi_pct:.2f}%)")
    print("─" * 72)
    print(f" 🎯 Tổng số lệnh đã đóng    : {total_trades} lệnh")
    print(f"    - Thắng (Win)           : {win_count} lệnh ({win_rate:.1f}%)")
    print(f"    - Thua (Loss)           : {loss_count} lệnh ({(loss_count / total_trades) * 100:.1f}%)" if total_trades > 0 else "    - Thua (Loss)           : 0 lệnh")
    if even_count > 0:
        print(f"    - Hòa                   : {even_count} lệnh")
    print("─" * 72)

    if not long_trades.empty:
        l_wins = len(long_trades[long_trades["pnl"] > 0])
        print(f" 🟢 Vị thế LONG             : {len(long_trades)} lệnh | Thắng: {l_wins}/{len(long_trades)} | PnL: {long_trades['pnl'].sum():+.2f} USDT")
    if not short_trades.empty:
        s_wins = len(short_trades[short_trades["pnl"] > 0])
        print(f" 🔴 Vị thế SHORT            : {len(short_trades)} lệnh | Thắng: {s_wins}/{len(short_trades)} | PnL: {short_trades['pnl'].sum():+.2f} USDT")

    best_trade = df["pnl"].max()
    worst_trade = df["pnl"].min()
    print("─" * 72)
    print(f" 🏆 Lệnh thắng đậm nhất     : {best_trade:+.2f} USDT")
    print(f" ⚠️  Lệnh thua nhiều nhất    : {worst_trade:+.2f} USDT")
    print("═" * 72)

    print("\n📋 CHI TIẾT CÁC GIAO DỊCH GẦN NHẤT:")
    display_cols = ["side", "entry_price", "exit_price", "pnl", "pnl_pct", "reason", "final_cash"]
    valid_cols = [c for c in display_cols if c in df.columns]

    recent_df = df[valid_cols].tail(5).copy()
    if "pnl" in recent_df.columns:
        recent_df["pnl"] = recent_df["pnl"].map(lambda x: f"{x:+.2f}")
    if "pnl_pct" in recent_df.columns:
        recent_df["pnl_pct"] = recent_df["pnl_pct"].map(lambda x: f"{x:+.2f}%")
    if "final_cash" in recent_df.columns:
        recent_df["final_cash"] = recent_df["final_cash"].map(lambda x: f"{x:,.2f}")

    print(recent_df.to_string(index=False))
    print("\n")


if __name__ == "__main__":
    print_summary()
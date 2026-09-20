# Crypto AI Paper Trader

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Edit `.env`, then train the Random Forest model:

```powershell
python train.py
python main.py
```

The model uses RSI(14), MACD, MACD signal, EMA(9), EMA(21), EMA spread, and volume change. A candle is labelled `BUY` when the 1.5% target is reached before the 1% stop-loss within the next five candles; otherwise it is `HOLD`.

The default campaign runs for 14 days, using 15-minute candles, 10% position sizing, 1% stop-loss, and 2% take-profit. The bot uses CCXT for public market data only and does not place real exchange orders.

"""Environment-backed settings for the paper trader."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    exchange_id: str = os.getenv("EXCHANGE_ID", "binance")
    symbol: str = os.getenv("SYMBOL", "BTC/USDT")
    timeframe: str = os.getenv("TIMEFRAME", "5m")
    initial_cash: float = float(os.getenv("INITIAL_CASH", "10000"))
    position_size_pct: float = float(os.getenv("POSITION_SIZE_PCT", "0.20"))
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "0.008"))
    take_profit_pct: float = float(os.getenv("TAKE_PROFIT_PCT", "0.02"))
    trailing_stop_pct: float = float(os.getenv("TRAILING_STOP_PCT", "0.002"))
    trailing_activation_pct: float = float(os.getenv("TRAILING_ACTIVATION_PCT", "0.004"))
    discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    candle_limit: int = int(os.getenv("CANDLE_LIMIT", "200"))
    loop_seconds: int = int(os.getenv("LOOP_SECONDS", "60"))
    campaign_days: int = int(os.getenv("CAMPAIGN_DAYS", "14"))


settings = Settings()

"""Cấu hình toàn bộ hệ thống Bot và tham số môi trường."""

import os
import math
from config.env import load_project_env

load_project_env()


class Settings:

  def __init__(self, *args, **kwargs):
    self.llm_mode = os.getenv("LLM_MODE", "LOCAL").upper()
    self.local_base_url = os.getenv(
        "LOCAL_LLM_BASE_URL", "http://localhost:11434/v1"
    )
    self.local_model = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:7b")
    self.local_api_key = os.getenv("LOCAL_LLM_API_KEY", "ollama")

    self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    self.groq_api_key = os.getenv("GROQ_API_KEY", "")
    self.groq_fallback_model = os.getenv(
        "GROQ_FALLBACK_MODEL", "qwen/qwen3.8-27b"
    )

    self.discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    self.exchange_id = os.getenv("EXCHANGE_ID", "binance").lower()
    self.symbol = os.getenv("SYMBOL", "BTC/USDT").upper()
    self.timeframe = os.getenv("TIMEFRAME", "5m").lower()
    self.initial_cash = float(os.getenv("INITIAL_CASH", "100"))
    self.position_size_pct = float(os.getenv("POSITION_SIZE_PCT", "0.10"))
    self.fee_rate = float(os.getenv("FEE_RATE", "0.0005"))
    self.stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "0.01"))
    self.take_profit_pct = float(os.getenv("TAKE_PROFIT_PCT", "0.02"))
    self.trailing_stop_pct = float(os.getenv("TRAILING_STOP_PCT", "0.008"))
    self.trailing_activation_pct = float(os.getenv("TRAILING_ACTIVATION_PCT", "0.01"))
    self.loop_seconds = float(os.getenv("LOOP_SECONDS", "15"))
    self.candle_limit = int(os.getenv("CANDLE_LIMIT", "250"))

    if self.exchange_id != "binance":
      raise ValueError("Luồng dữ liệu hiện tại chỉ hỗ trợ EXCHANGE_ID=binance")
    if "/" not in self.symbol or ":" in self.symbol:
      raise ValueError("SYMBOL cần ở dạng spot BASE/QUOTE, ví dụ BTC/USDT")
    if not math.isfinite(self.initial_cash) or self.initial_cash <= 0:
      raise ValueError("INITIAL_CASH phải lớn hơn 0")
    if not math.isfinite(self.position_size_pct) or not 0 < self.position_size_pct <= 1:
      raise ValueError("POSITION_SIZE_PCT phải nằm trong (0, 1]")
    if not math.isfinite(self.fee_rate) or not 0 <= self.fee_rate < 1:
      raise ValueError("FEE_RATE phải nằm trong [0, 1)")
    for name in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "trailing_activation_pct"):
      value = getattr(self, name)
      if not math.isfinite(value) or value <= 0 or value >= 1:
        raise ValueError(f"{name.upper()} phải nằm trong (0, 1)")
    if not math.isfinite(self.loop_seconds) or self.loop_seconds <= 0:
      raise ValueError("LOOP_SECONDS phải lớn hơn 0")
    if not 31 <= self.candle_limit <= 1000:
      raise ValueError("CANDLE_LIMIT phải nằm trong [31, 1000]")

  @property
  def api_symbol(self) -> str:
    return self.symbol.replace("/", "").replace(":", "")

  def __getitem__(self, key: str):
    return getattr(self, key.lower(), os.getenv(key, ""))

  def get(self, key: str, default=None):
    return getattr(self, key.lower(), os.getenv(key, default))


# Hỗ trợ cả 2 tên gọi để không bị lỗi import
Config = Settings
settings = Settings()

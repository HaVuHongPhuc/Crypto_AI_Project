"""Cấu hình toàn bộ hệ thống Bot và tham số môi trường."""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
  load_dotenv(dotenv_path=ENV_FILE, encoding="utf-8")


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
    self.symbol = "BTC/USDT"
    self.timeframe = "5m"

  def __getitem__(self, key: str):
    return getattr(self, key.lower(), os.getenv(key, ""))

  def get(self, key: str, default=None):
    return getattr(self, key.lower(), os.getenv(key, default))


# Hỗ trợ cả 2 tên gọi để không bị lỗi import
Config = Settings
settings = Settings()

"""SentimentAgent: Tác tử Tình báo Thị trường & Tin tức Vĩ mô."""

from datetime import datetime, timezone
import json
import logging
import time
import xml.etree.ElementTree as ET
import requests


class SentimentAgent:

  SYSTEM_PROMPT = """
    You are the Chief Market Intelligence & Sentiment Officer for a Crypto Quantitative Fund.
    Your mission: Analyze breaking crypto news headlines and the Fear & Greed Index to assess systemic risks.

    CRITICAL FOCUS:
    - Detect 'BLACK SWAN' events: Exchange hacks, sudden SEC crackdowns, de-pegging, major macro liquidation cascading.
    - Rate Panic Level from 1 (Extreme Euphoria/Calm) to 10 (Total Market Meltdown).

    Output ONLY raw valid JSON:
    {
      "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
      "panic_score": 1 to 10,
      "black_swan_alert": true | false,
      "key_driver": "Tóm tắt ngắn gọn sự kiện (dưới 20 từ tiếng Việt)",
      "trading_advice": "NORMAL" | "CAUTION" | "HALT_TRADING"
    }
    """

  def __init__(self, config=None, cache_ttl_seconds: int = 900):
    self.config = config
    self.cache_ttl = cache_ttl_seconds
    self.last_fetch_time = 0
    self.cached_result = {
        "sentiment": "NEUTRAL",
        "panic_score": 5,
        "black_swan_alert": False,
        "key_driver": "Khởi tạo hệ thống tin tức",
        "trading_advice": "NORMAL",
        "fear_and_greed": 50,
        "fear_classification": "Neutral",
    }

  def _fetch_fear_and_greed(self) -> dict:
    try:
      res = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
      if res.status_code == 200:
        data = res.json().get("data", [{}])[0]
        return {
            "value": int(data.get("value", 50)),
            "classification": data.get("value_classification", "Neutral"),
        }
    except Exception:
      pass
    return {"value": 50, "classification": "Neutral"}

  def _fetch_crypto_headlines(self, limit: int = 6) -> list:
    headlines = []
    try:
      headers = {"User-Agent": "Mozilla/5.0"}
      resp = requests.get(
          "https://cointelegraph.com/rss", headers=headers, timeout=8
      )
      if resp.status_code == 200:
        root = ET.fromstring(resp.content)
        for item in root.findall("./channel/item")[:limit]:
          title = item.find("title")
          if title is not None and title.text:
            headlines.append(title.text.strip())
    except Exception as e:
      logging.warning("Không thể cào tin tức RSS: %s", str(e))
    return headlines

  def analyze_market_sentiment(self, force_refresh: bool = False) -> dict:
    # Lazy import để triệt tiêu hoàn toàn lỗi Circular Import
    from agents.agent_team import _ask_llm

    current_time = time.time()
    if (
        not force_refresh
        and (current_time - self.last_fetch_time) < self.cache_ttl
    ):
      return self.cached_result

    logging.info(">>> [SENTIMENT AGENT] Đang quét tin tức thị trường mới nhất...")
    fng = self._fetch_fear_and_greed()
    headlines = self._fetch_crypto_headlines(limit=6)

    news_text = (
        "\n".join([f"- {h}" for h in headlines])
        if headlines
        else "Không có tin giật gân đáng chú ý."
    )

    user_prompt = f"""
DỮ LIỆU TÂM LÝ & TIN TỨC CRYPTO HIỆN TẠI:
- Chỉ số Fear & Greed: {fng['value']}/100 ({fng['classification']})
- 6 Tiêu đề tin tức nóng nhất vừa cập nhật:
{news_text}

Hãy phân tích mức độ hoảng loạn, rủi ro tin xấu bất ngờ và đưa ra đánh giá tình báo dạng JSON.
"""
    result = _ask_llm(self.SYSTEM_PROMPT, user_prompt)

    if isinstance(result, dict) and "sentiment" in result:
      result["fear_and_greed"] = fng["value"]
      result["fear_classification"] = fng["classification"]
      self.cached_result = result
      self.last_fetch_time = current_time

      logging.info(
          ">>> [SENTIMENT ĐÃ DUYỆT] Tâm lý: %s | Hoảng loạn: %s/10 | Lời khuyên:"
          " %s | Sự kiện: %s",
          result.get("sentiment"),
          result.get("panic_score"),
          result.get("trading_advice"),
          result.get("key_driver"),
      )
      return result

    return self.cached_result
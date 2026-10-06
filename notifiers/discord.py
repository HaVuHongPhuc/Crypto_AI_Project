"""Module gửi thông báo qua Discord Webhook."""

import logging
import os
import requests


class DiscordNotifier:

  def __init__(self, webhook_url: str = None):
    self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")

  def send(self, message: str):
    if not self.webhook_url:
      return
    try:
      response = requests.post(self.webhook_url, json={"content": message}, timeout=5)
      response.raise_for_status()
    except Exception as e:
      logging.warning("Discord send failed: %s", e)

  def send_embed(self, title: str, description: str, color: int = 0x3498DB):
    if not self.webhook_url:
      return
    payload = {
        "embeds": [{"title": title, "description": description, "color": color}]
    }
    try:
      response = requests.post(self.webhook_url, json=payload, timeout=5)
      response.raise_for_status()
    except Exception as e:
      logging.warning("Discord embed send failed: %s", e)

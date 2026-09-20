"""Discord webhook notifications."""

import requests


def send_message(webhook_url: str, title: str, message: str, color: int = 0x2ECC71) -> None:
    if not webhook_url:
        return
    payload = {"embeds": [{"title": title, "description": message, "color": color}]}
    response = requests.post(webhook_url, json=payload, timeout=10)
    response.raise_for_status()

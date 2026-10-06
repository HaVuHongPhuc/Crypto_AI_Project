"""Discord webhook notifications with consistent, detailed embed cards."""

from datetime import datetime, timezone
import logging
import os

import requests


class DiscordNotifier:
    EMBED_TOTAL_LIMIT = 6000
    DESCRIPTION_LIMIT = 4096
    FIELD_NAME_LIMIT = 256
    FIELD_VALUE_LIMIT = 1024

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")

    @staticmethod
    def _trim(value, limit: int) -> str:
        text = str(value or "—").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

    def _post(self, payload: dict, message_kind: str) -> bool:
        if not self.webhook_url:
            logging.debug("Discord %s skipped: webhook is not configured", message_kind)
            return False
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=8,
            )
            response.raise_for_status()
            logging.info("Discord %s delivered (HTTP %s)", message_kind, response.status_code)
            return True
        except Exception as exc:
            # Never log the exception or URL: webhook URLs contain a secret token.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            logging.warning(
                "Discord %s failed (%s%s)",
                message_kind,
                type(exc).__name__,
                f", HTTP {status}" if status else "",
            )
            return False

    def send(self, message: str) -> bool:
        """Backward-compatible plain text notification."""
        return self._post(
            {
                "content": self._trim(message, 2000),
                "allowed_mentions": {"parse": []},
            },
            "message",
        )

    def send_embed(
        self,
        title: str,
        description: str = "",
        color: int = 0x3498DB,
        fields: list = None,
        footer: str = None,
    ) -> bool:
        """Send a Discord embed; fields are dictionaries with name/value/inline."""
        title = self._trim(title, 256)
        description = self._trim(description, self.DESCRIPTION_LIMIT) if description else ""
        embed = {
            "title": title,
            "color": int(color),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if description:
            embed["description"] = description

        clean_fields = []
        total_text = len(title) + len(description)
        for field in fields or []:
            if not isinstance(field, dict):
                continue
            name = self._trim(field.get("name", "Thông tin"), self.FIELD_NAME_LIMIT)
            value = self._trim(field.get("value", "—"), self.FIELD_VALUE_LIMIT)
            if total_text + len(name) + len(value) > self.EMBED_TOTAL_LIMIT:
                break
            clean_fields.append({
                "name": name,
                "value": value,
                "inline": bool(field.get("inline", False)),
            })
            total_text += len(name) + len(value)
        if clean_fields:
            embed["fields"] = clean_fields
        if footer:
            embed["footer"] = {"text": self._trim(footer, 2048)}

        logging.info(
            "Discord embed prepared: %s | sections: %s",
            title,
            " • ".join(field["name"] for field in clean_fields) or "description only",
        )

        return self._post(
            {"embeds": [embed], "allowed_mentions": {"parse": []}},
            "embed",
        )

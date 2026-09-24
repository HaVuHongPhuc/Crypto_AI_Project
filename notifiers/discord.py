"""Module gửi thông báo qua Discord Webhook."""

import os
import logging
from datetime import datetime, timezone
import requests

logger = logging.getLogger("CryptoAI")


class DiscordNotifier:

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")

    def _post(self, payload: dict) -> bool:
        if not self.webhook_url:
            logger.warning("Discord Webhook URL chưa được cấu hình!")
            return False
        try:
            res = requests.post(self.webhook_url, json=payload, timeout=5)
            if res.status_code not in (200, 204):
                logger.error(f"❌ Discord từ chối (Mã {res.status_code}): {res.text}")
                return False
            return True
        except Exception as e:
            logger.warning(f"Discord post failed: {e}")
            return False

    def send(self, message: str):
        """Gửi tin nhắn văn bản thô đơn giản."""
        return self._post({"content": message})

    def send_trade_open(
        self,
        side: str,
        symbol: str,
        price: float,
        capital: float,
        macro_directive: str,
        rules_version: int,
        operator_reason: str,
        supervisor_reason: str,
        total_equity: float = 100.0,
        available_cash: float = 30.0
    ):
        """Card Embed Mở Vị Thế [AI TEAM]."""
        color = 0xE67E22 if side.upper() == "SHORT" else 0x2ECC71

        description_text = (
            f"**Cặp:** {symbol} @ {price:,.6f}\n"
            f"**Vị thế:** {side.upper()} | **Khối lượng:** {capital:,.6f} USDT\n"
            f"💰 **Ví:** `{total_equity:,.2f} USDT` (Khả dụng: `{available_cash:,.2f} USDT`)\n"
            f"**Chỉ thị 1H:** {macro_directive} | **Bộ luật:** v{rules_version}\n"
            f"**Operator:** {operator_reason}\n"
            f"**Supervisor:** {supervisor_reason}"
        )

        payload = {
            "embeds": [
                {
                    "title": f"🟢 [AI TEAM] Paper Trade Mở: {side.upper()}",
                    "description": description_text,
                    "color": color,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            ]
        }
        return self._post(payload)

    def send_trade_close(
        self,
        exit_type: str,
        side: str,
        symbol: str,
        entry_price: float,
        exit_price: float,
        pnl_usdt: float,
        pnl_pct: float,
        total_equity: float,
        cum_pnl_usdt: float = 0.0,
        cum_pnl_pct: float = 0.0,
        reflector_lesson: str = "Tuân thủ kỷ luật giao dịch."
    ):
        """
        Khôi phục nguyên bản Card Embed [KẾT QUẢ GIAO DỊCH]:
        - Tiêu đề: 🔔 [KẾT QUẢ GIAO DỊCH] kèm lý do thoát (AI_EARLY_EXIT_CLOSE, TP, SL)
        - Viền: Xanh lá (0x2ECC71) nếu có lãi, Đỏ/Cam (0xE74C3C) nếu lỗ
        - Hiển thị đầy đủ: Lãi/Lỗ lệnh, Tổng vốn, Lãi/lỗ tích lũy và Bài học Reflector
        """
        color = 0x2ECC71 if pnl_pct >= 0 else 0xE74C3C

        description_text = (
            f"**Cặp:** {symbol} | **Vị thế:** {side.upper()}\n"
            f"**Giá vào:** {entry_price:,.6f} ➔ **Giá đóng:** {exit_price:,.6f}\n"
            f"─────────────────────────────\n"
            f"💵 **Lãi/Lỗ lệnh này:** `{pnl_usdt:+.6f} USDT` (`{pnl_pct:+.2f}%`)\n"
            f"💰 **TỔNG VỐN HIỆN TẠI:** `{total_equity:,.6f} USDT`\n"
            f"📈 **TỔNG LÃI/LỖ TÍCH LŨY:** `{cum_pnl_usdt:+.6f} USDT` (`{cum_pnl_pct:+.2f}%`)\n"
            f"🧠 **Bài học Reflector:** {reflector_lesson}"
        )

        payload = {
            "embeds": [
                {
                    "title": f"🔔 [KẾT QUẢ GIAO DỊCH]\n{exit_type}",
                    "description": description_text,
                    "color": color,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            ]
        }
        return self._post(payload)

    def send_strategist_update(
        self,
        directive: str,
        macro_bias: str,
        reasoning: str,
        total_equity: float = 100.0,
        available_cash: float = 100.0
    ):
        """Card Embed Strategist 1H hiển thị xu hướng và phân bổ vốn quỹ."""
        description_text = (
            f"**Xu hướng 1H:** {macro_bias.upper()}\n"
            f"**Chiến lược:** {reasoning}\n"
            f"💰 **Tài sản quỹ:** `{total_equity:,.2f} USDT` (Khả dụng: `{available_cash:,.2f} USDT`)"
        )

        payload = {
            "embeds": [
                {
                    "title": f"🧭 [STRATEGIST 1H] Chỉ Thị Vĩ Mô:\n{directive.upper()}",
                    "description": description_text,
                    "color": 0x3498DB,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            ]
        }
        return self._post(payload)
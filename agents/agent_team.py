"""Multi-Agent System for Crypto Trading: Operator, Supervisor, and Auditor."""

import json
import os
from openai import OpenAI

# Khởi tạo client kết nối LLM
client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
)
MODEL = os.getenv("LLM_MODEL_NAME", "gpt-4o-mini")


def _ask_llm(system_prompt: str, user_prompt: str) -> dict:
    """Hàm phụ trợ gọi LLM và ép kiểu dữ liệu trả về thành JSON."""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2  # Giữ nhiệt độ thấp để AI tư duy logic, không bịa đặt
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"error": str(e)}


# -------------------------------------------------------------
# 1. AI OPERATOR: Phân tích kỹ thuật & đề xuất kế hoạch
# -------------------------------------------------------------
class OperatorAgent:
    SYSTEM_PROMPT = """
    You are a Quantitative Crypto Trader specialized in bi-directional Futures (Long & Short).
    CRITICAL: Output ONLY a valid raw JSON object. No conversational filler or explanations.

    Your action must be one of:
    - "OPEN_LONG": Enter long when trend is upward, EMA9 > EMA21, RSI > 50.
    - "OPEN_SHORT": Enter short when trend is downward, EMA9 < EMA21, RSI < 50.
    - "CLOSE": Close current active position due to trend reversal.
    - "HOLD": No clear signal or market is ranging.

    JSON format:
    {
      "action": "OPEN_LONG" | "OPEN_SHORT" | "CLOSE" | "HOLD",
      "confidence": 0.0 to 1.0,
      "reason": "Clear technical reasoning"
    }
    """

    def analyze(self, symbol: str, current_price: float, indicators: dict) -> dict:
        user_prompt = f"""
        Thị trường: {symbol}
        Giá hiện tại: {current_price}
        Chỉ số kỹ thuật:
        - RSI (14): {indicators.get('rsi_14', 'N/A')}
        - MACD: {indicators.get('macd', 'N/A')} (Signal: {indicators.get('macd_signal', 'N/A')})
        - EMA 9: {indicators.get('ema_9', 'N/A')} | EMA 21: {indicators.get('ema_21', 'N/A')}
        - Độ biến động Volume: {indicators.get('volume_change', 'N/A')}
        
        Hãy đưa ra quyết định giao dịch dạng JSON.
        """
        return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 2. AI SUPERVISOR: Giám sát rủi ro & Phê duyệt lệnh
# -------------------------------------------------------------
class SupervisorAgent:
    SYSTEM_PROMPT = """
    Bạn là Giám đốc Quản trị Rủi ro (Supervisor Agent).
    Nhiệm vụ: Phản biện và xét duyệt đề xuất từ Operator Agent trước khi chuyển xuống sàn.

    Strict Rules for Approval:
    1. Reject OPEN_LONG if RSI > 70 (Overbought - risk of buying the top).
    2. Reject OPEN_SHORT if RSI < 30 (Oversold - risk of shorting the bottom).
    3. Reject if confidence is below 0.60.
    4. Automatically approve HOLD.

    JSON format:
    {
      "approved": true | false,
      "risk_score": 1 to 10,
      "feedback": "Reason for decision"
    }
    """

    def review(self, proposal: dict, indicators: dict, cash: float) -> dict:
        action = proposal.get("action")
        # HOLD và CLOSE không mở thêm rủi ro mới nên mặc định duyệt.
        if action in ("HOLD", "CLOSE"):
            return {"approved": True, "risk_score": 1, "feedback": f"{action} không phát sinh rủi ro mới, tự động duyệt."}

        user_prompt = f"""
        Đề xuất từ Operator: {json.dumps(proposal)}
        Chỉ số thị trường: {json.dumps(indicators)}
        Vốn hiện tại: {cash} USDT
        
        Hãy thẩm định đề xuất này và trả về JSON.
        """
        return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 3. AI AUDITOR: Giám sát lỗi hệ thống & Đề xuất khắc phục
# -------------------------------------------------------------
class AuditorAgent:
    SYSTEM_PROMPT = """
    Bạn là Kỹ sư SRE / Hệ thống (Auditor Agent) giám sát Trading Bot 24/7.
    Nhiệm vụ: Đọc traceback log lỗi khi bot gặp sự cố (Network, Sàn sập, Logic sai) để chẩn đoán.
    
    Định dạng đầu ra JSON bắt buộc:
    {
      "severity": "WARNING" | "CRITICAL",
      "diagnosis": "Giải thích lỗi bằng tiếng Việt ngắn gọn, dễ hiểu cho admin",
      "suggested_action": "Hành động bot nên làm (Sleep 60s / Thử lại / Dừng khẩn cấp)"
    }
    You are a Site Reliability Engineer (Auditor Agent).
    CRITICAL: You must output ONLY a valid JSON object. Do not output any conversational text or explanation outside the JSON.

    Format:
    {
    "severity": "WARNING" | "CRITICAL",
    "diagnosis": "Short diagnosis in Vietnamese",
    "suggested_action": "Action to take"
    }
    """

    def inspect_error(self, traceback_str: str) -> dict:
        user_prompt = f"Hệ thống vừa văng lỗi Exception sau:\n{traceback_str}\nHãy phân tích và trả về JSON."
        return _ask_llm(self.SYSTEM_PROMPT, user_prompt)
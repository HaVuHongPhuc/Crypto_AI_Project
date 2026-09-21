"""Multi-Agent System for Crypto Trading: Operator, Supervisor, and Auditor."""

import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Tự động nạp file .env từ thư mục gốc
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Khởi tạo client kết nối LLM có timeout 30s chống treo socket
client = OpenAI(
    api_key=os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    timeout=30.0,
)
MODEL = os.getenv("LLM_MODEL_NAME", "llama-3.3-70b-versatile")


def _ask_llm(system_prompt: str, user_prompt: str) -> dict:
  """Hàm phụ trợ gọi LLM, ép kiểu JSON và điều tiết tốc độ tránh lỗi 429."""
  time.sleep(1)  # Khoảng nghỉ 1 giây giúp tránh chạm Rate Limit của Groq
  try:
    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return json.loads(response.choices[0].message.content)
  except Exception as e:
    return {"error": str(e)}


# -------------------------------------------------------------
# 1. AI OPERATOR: Phân tích kỹ thuật & Đề xuất kế hoạch
# -------------------------------------------------------------
class OperatorAgent:
  SYSTEM_PROMPT = """
    You are a Quantitative Crypto Trader specialized in bi-directional Futures (Long & Short) on the 5m timeframe.
    CRITICAL: Output ONLY a valid raw JSON object.

    ACTION RULES BASED ON CURRENT POSITION:
    1. When position is EMPTY (side == "NONE"):
       - "OPEN_LONG": Enter long when EMA9 > EMA21, RSI > 50, MACD momentum is expanding upward.
       - "OPEN_SHORT": Enter short when EMA9 < EMA21, RSI < 50, MACD momentum is expanding downward.
       - "HOLD": Sideway, conflicting indicators, or no clear edge.

    2. When HOLDING a position (side == "LONG" or "SHORT"):
       - "HOLD": The trend still favors the current position. Keep holding to maximize profit.
       - "CLOSE": EARLY EXIT! Immediately close the position if the market shows clear signs of reversal:
         * If holding LONG and price breaks below EMA9/EMA21, RSI drops below 48, or MACD turns bearish.
         * If holding SHORT and price breaks above EMA9/EMA21, RSI crosses above 52, or MACD turns bullish.
       - NEVER propose "OPEN_LONG" while holding SHORT, or "OPEN_SHORT" while holding LONG. You must "CLOSE" first!

    JSON format:
    {
      "action": "OPEN_LONG" | "OPEN_SHORT" | "CLOSE" | "HOLD",
      "confidence": 0.0 to 1.0,
      "reason": "Clear technical reasoning explaining momentum, indicators, and current position PnL"
    }
    """

  def analyze(
      self,
      symbol: str,
      current_price: float,
      indicators: dict,
      position_info: dict = None,
  ) -> dict:
    # Giá trị mặc định nếu chưa có vị thế
    if not position_info:
      position_info = {
          "side": "NONE",
          "entry_price": 0.0,
          "pnl_pct": 0.0,
          "pnl_usdt": 0.0,
          "holding_candles": 0,
      }

    user_prompt = f"""
        Thị trường: {symbol}
        Giá hiện tại: {current_price} USDT
        
        --- TRẠNG THÁI VỊ THẾ HIỆN TẠI ---
        - Vị thế: {position_info.get('side', 'NONE')}
        - Giá vào lệnh: {position_info.get('entry_price', 0.0)} USDT
        - PnL tạm tính: {position_info.get('pnl_pct', 0.0):.2f}% ({position_info.get('pnl_usdt', 0.0):.4f} USDT)
        - Số nến đã gồng: {position_info.get('holding_candles', 0)} nến 5m

        --- CHỈ SỐ KỸ THUẬT NẾN 5M ---
        - RSI (14): {indicators.get('rsi_14', indicators.get('rsi', 'N/A'))}
        - MACD: {indicators.get('macd', 'N/A')} (Signal: {indicators.get('macd_signal', 'N/A')})
        - EMA 9: {indicators.get('ema_9', indicators.get('ema9', 'N/A'))} | EMA 21: {indicators.get('ema_21', indicators.get('ema21', 'N/A'))}
        - Biến động Volume: {indicators.get('volume_change', 'N/A')}
        - Dự báo ML Model: {indicators.get('ml_signal', 'HOLD')}
        
        Hãy đưa ra quyết định giao dịch dạng JSON (OPEN_LONG / OPEN_SHORT / CLOSE / HOLD).
        """
    return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 2. AI SUPERVISOR: Giám sát rủi ro & Phê duyệt lệnh
# -------------------------------------------------------------
class SupervisorAgent:
  SYSTEM_PROMPT = """
    Bạn là Giám đốc Quản trị Rủi ro (Supervisor Agent).
    Nhiệm vụ: Phản biện và xét duyệt đề xuất từ Operator Agent dựa trên quy tắc an toàn vốn.

    Quy tắc kiểm duyệt (Strict Rules for Approval):
    1. Đề xuất HOLD hoặc CLOSE: Luôn DUYỆT (approved = true, risk_score = 1). CLOSE giúp cắt lỗ sớm hoặc chốt lời an toàn.
    2. Đề xuất OPEN_LONG:
       - Từ chối nếu RSI > 75 (Quá mua - rủi ro đu đỉnh).
       - Từ chối nếu tài khoản đang giữ lệnh SHORT chưa đóng.
    3. Đề xuất OPEN_SHORT:
       - Từ chối nếu RSI < 25 (Quá bán - rủi ro bắt đáy short squeeze).
       - Từ chối nếu tài khoản đang giữ lệnh LONG chưa đóng.
    4. Độ tin cậy (confidence): Từ chối nếu Operator có confidence < 0.60.

    Định dạng đầu ra JSON bắt buộc:
    {
      "approved": true | false,
      "risk_score": 1 to 10,
      "feedback": "Lý do duyệt hoặc từ chối ngắn gọn"
    }
    """

  def review(
      self,
      proposal: dict,
      indicators: dict,
      cash: float,
      position_info: dict = None,
  ) -> dict:
    action = proposal.get("action")

    # HOLD và CLOSE giảm rủi ro tài khoản, tự động duyệt không cần tốn token API
    if action in ("HOLD", "CLOSE"):
      return {
          "approved": True,
          "risk_score": 1,
          "feedback": f"{action} không phát sinh rủi ro mở mới, tự động duyệt.",
      }

    if not position_info:
      position_info = {"side": "NONE"}

    user_prompt = f"""
        Đề xuất từ Operator: {json.dumps(proposal, ensure_ascii=False)}
        Vị thế hiện tại: {json.dumps(position_info, ensure_ascii=False)}
        Chỉ số thị trường: {json.dumps(indicators, ensure_ascii=False)}
        Vốn khả dụng: {cash} USDT
        
        Hãy thẩm định đề xuất này và trả về JSON.
        """
    return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 3. AI AUDITOR: Giám sát lỗi hệ thống & Đề xuất khắc phục
# -------------------------------------------------------------
class AuditorAgent:
  SYSTEM_PROMPT = """
    Bạn là Kỹ sư SRE / Hệ thống (Auditor Agent) giám sát Trading Bot 24/7.
    Nhiệm vụ: Đọc traceback log lỗi khi bot gặp sự cố để chẩn đoán nguyên nhân và đưa ra hành động khắc phục.
    
    Định dạng đầu ra JSON bắt buộc:
    {
      "severity": "WARNING" | "CRITICAL",
      "diagnosis": "Giải thích lỗi bằng tiếng Việt ngắn gọn, dễ hiểu cho admin",
      "suggested_action": "Hành động bot nên làm (Sleep 60s / Thử lại / Dừng khẩn cấp)"
    }
    """

  def inspect_error(self, traceback_str: str) -> dict:
    user_prompt = f"""Hệ thống vừa văng lỗi Exception sau:
{traceback_str}
Hãy phân tích và trả về JSON."""
    return _ask_llm(self.SYSTEM_PROMPT, user_prompt)
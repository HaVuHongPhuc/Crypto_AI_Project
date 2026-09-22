"""Multi-Agent System for Crypto Trading with Self-Improving Architecture:
1. StrategistAgent - Định hướng xu hướng lớn khung 1H (Nhạc trưởng)
2. OperatorAgent   - Thực thi Scalping nến 5m theo Bộ luật Động (Chân ga)
3. SupervisorAgent - Quản trị rủi ro & Duyệt lệnh (Chân phanh)
4. ReflectorAgent  - Đúc rút bài học & TỰ ĐỘNG NÂNG CẤP BỘ LUẬT (Tự học)
5. AuditorAgent    - SRE trực ban bắt lỗi Exception hệ thống
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from dotenv import load_dotenv
from openai import OpenAI

# Tự động nạp file .env từ thư mục gốc
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# 1. Khởi tạo client kết nối Gemini API (Bộ não chính)
client = OpenAI(
    api_key=os.getenv("LLM_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or os.getenv("GROQ_API_KEY"),
    base_url=os.getenv(
        "LLM_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    timeout=30.0,
)
MODEL = os.getenv("LLM_MODEL_NAME", "gemini-3.1-flash-lite")

# 2. Khởi tạo client phụ Groq (Phao cứu hộ khi Gemini bị lỗi 503)
groq_client = (
    OpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
        timeout=15.0,
    )
    if os.getenv("GROQ_API_KEY")
    else None
)
GROQ_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "qwen/qwen3.8-27b")

# Đường dẫn lưu trữ bộ nhớ và luật động
MEMORY_FILE = BASE_DIR / "storage" / "memory.json"
RULES_FILE = BASE_DIR / "storage" / "strategy_rules.json"

DEFAULT_RULES = {
    "version": 1,
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "reason_for_update": "Bộ quy tắc khởi tạo mặc định cho Scalping 5m",
    "entry_rules": (
        "OPEN_LONG khi EMA9 > EMA21 và RSI > 50 (tuân thủ chỉ thị 1H)."
        " OPEN_SHORT khi EMA9 < EMA21 và RSI < 50 (tuân thủ chỉ thị 1H)."
    ),
    "exit_rules": (
        "GIVE TRADES ROOM TO BREATHE: Giữ lệnh HOLD khi giá chỉ nhúng nhẹ chạm"
        " EMA9 trong xu hướng mạnh. CHỈ ĐÓNG (CLOSE) khi nến đóng gãy hẳn qua"
        " EMA21 hoặc khi lợi nhuận đạt >= 0.8% để khóa lãi an toàn."
    ),
}


def _ask_llm(system_prompt: str, user_prompt: str) -> dict:
  """Gọi Gemini; nếu Google quá tải 503, tự động chuyển ngay sang Groq cứu hộ."""
  time.sleep(0.5)

  # 1. Thử gọi Google Gemini
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
    err_str = str(e)
    logging.warning("⚠️ Google Gemini gặp sự cố (503/Timeout): %s", err_str[:70])

  # 2. Phao cứu sinh: Tự động kích hoạt Groq nếu Google lỗi
  if groq_client:
    try:
      logging.info(
          ">>> [FAILOVER CỨU HỘ] Đang chuyển sang Groq (%s)...", GROQ_MODEL
      )
      response = groq_client.chat.completions.create(
          model=GROQ_MODEL,
          response_format={"type": "json_object"},
          messages=[
              {"role": "system", "content": system_prompt},
              {"role": "user", "content": user_prompt},
          ],
          temperature=0.2,
      )
      return json.loads(response.choices[0].message.content)
    except Exception as groq_err:
      logging.error("Lỗi cả Groq: %s", str(groq_err))

  return {"error": "Tat ca LLM deu gap su co"}


# -------------------------------------------------------------
# 1. STRATEGIST AGENT: Định hướng xu hướng lớn (Khung 1H)
# -------------------------------------------------------------
class StrategistAgent:

  SYSTEM_PROMPT = """
    You are the Senior Chief Strategist for a Crypto Quantitative Fund.
    Your role is to analyze the MACRO TREND on the 1-HOUR (1H) TIMEFRAME.
    You dictate whether the 5m Scalper is allowed to go LONG, SHORT, or BOTH.

    RULES FOR DIRECTIVE:
    - "ONLY_LONG" : 1H Price > EMA50, EMA50 > EMA200, RSI_1H > 52. Strong Bullish. 5m scalper must NEVER open Short.
    - "ONLY_SHORT": 1H Price < EMA50, EMA50 < EMA200, RSI_1H < 48. Strong Bearish. 5m scalper must NEVER open Long.
    - "FLEXIBLE"  : Market is in a 1H consolidation or range. Both Long and Short scalps are permitted.

    JSON format:
    {
      "macro_bias": "BULLISH" | "BEARISH" | "SIDEWAY",
      "directive": "ONLY_LONG" | "ONLY_SHORT" | "FLEXIBLE",
      "reasoning": "Clear macro explanation"
    }
    """

  def analyze_macro(
      self, symbol: str, current_price: float, h1_ind: dict
  ) -> dict:
    user_prompt = f"""
Thị trường: {symbol} | Giá hiện tại: {current_price} USDT
DỮ LIỆU KHUNG 1H (H1):
- RSI(14) 1H: {h1_ind.get('rsi_14', 'N/A')}
- MACD 1H: {h1_ind.get('macd', 'N/A')}
- EMA50 1H: {h1_ind.get('ema_50', 'N/A')} | EMA200 1H: {h1_ind.get('ema_200', 'N/A')}
- Giá hiện tại so với EMA50 1H: {'TRÊN' if current_price >= h1_ind.get('ema_50', current_price) else 'DƯỚI'}

Hãy ban hành chỉ thị xu hướng 1H cho đội ngũ Scalp 5m dạng JSON.
"""
    return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 2. OPERATOR AGENT: Thực thi nến 5m theo Bộ Luật Động (CHÂN GA)
# -------------------------------------------------------------
class OperatorAgent:

  SYSTEM_PROMPT = """
    You are an Aggressive Scalping Trader on the 5m crypto timeframe.
    Your sole focus is TREND DIRECTION and FAST EXECUTION following the DYNAMIC STRATEGY RULES.
    CRITICAL: Output ONLY a valid raw JSON object.

    CORE PRINCIPLE:
    Volume is secondary. Respect the Strategist's MACRO DIRECTIVE and strictly apply the DYNAMIC ENTRY & EXIT RULES provided in the prompt.

    ACTION RULES (When position is EMPTY):
    - Apply the Dynamic Entry Rules. Respect Directive (Do not OPEN_LONG if ONLY_SHORT; do not OPEN_SHORT if ONLY_LONG).
    - Propose "HOLD" if EMA lines are flat/tangled (difference < 3 USD) or if rules are not satisfied.

    ACTION RULES (When HOLDING a position):
    - Apply the Dynamic Exit Rules. Do NOT panic-close on minor pullbacks if the rules instruct to give room.
    - NEVER propose "OPEN_LONG" while holding SHORT, or "OPEN_SHORT" while holding LONG. Propose "CLOSE" first!

    JSON format:
    {
      "action": "OPEN_LONG" | "OPEN_SHORT" | "CLOSE" | "HOLD",
      "confidence": 0.60 to 0.95,
      "reason": "Direct technical trigger referencing the dynamic rules"
    }
    """

  def analyze(
      self,
      symbol: str,
      current_price: float,
      indicators: dict,
      position_info: dict = None,
      macro_directive: str = "FLEXIBLE",
  ) -> dict:
    if not position_info:
      position_info = {
          "side": "NONE",
          "entry_price": 0.0,
          "pnl_pct": 0.0,
          "pnl_usdt": 0.0,
          "holding_candles": 0,
      }

    rules = ReflectorAgent.load_rules()

    rsi_val = float(indicators.get("rsi_14", 50))
    ema9_val = float(indicators.get("ema_9", current_price))
    ema21_val = float(indicators.get("ema_21", current_price))

    rsi_state = (
        "TRÊN 50 (BULLISH)" if rsi_val > 50 else "DƯỚI 50 (BEARISH / SHORT)"
    )
    ema_state = (
        "EMA9 > EMA21 (TĂNG / LONG)"
        if ema9_val > ema21_val
        else "EMA9 < EMA21 (GIẢM / SHORT)"
    )
    ema_diff = abs(ema9_val - ema21_val)
    is_tangled = (
        "CÓ (TANGLED/SIDEWAY - KHÔNG NÊN VÀO)"
        if ema_diff < 3.0
        else f"KHÔNG (TÁCH BIỆT {ema_diff:.2f} USDT)"
    )

    user_prompt = f"""
Thị trường: {symbol} | Giá hiện tại: {current_price} USDT
CHỈ THỊ VĨ MÔ 1H TỪ STRATEGIST: [{macro_directive}]

--- BỘ QUY TẮC CHIẾN THUẬT TỰ ĐỘNG CẬP NHẬT (PHIÊN BẢN v{rules.get('version', 1)}) ---
- Lý do cập nhật gần nhất: {rules.get('reason_for_update', 'Mặc định')}
- QUY TẮC VÀO LỆNH (Entry Rules): {rules.get('entry_rules')}
- QUY TẮC THOÁT LỆNH (Exit Rules): {rules.get('exit_rules')}

--- TRẠNG THÁI VỊ THẾ HIỆN TẠI ---
- Vị thế: {position_info.get('side', 'NONE')}
- Giá vào lệnh: {position_info.get('entry_price', 0.0)} USDT
- PnL tạm tính: {position_info.get('pnl_pct', 0.0):.2f}% ({position_info.get('pnl_usdt', 0.0):.4f} USDT)
- Số nến đã gồng: {position_info.get('holding_candles', 0)} nến 5m

--- PHÂN TÍCH KỸ THUẬT ĐÃ ĐƯỢC XÁC THỰC (PYTHON PRE-COMPUTED) ---
- RSI(14) thực tế = {rsi_val} ➔ Kết luận: {rsi_state}
- Cấu trúc EMA: EMA9 ({ema9_val}) vs EMA21 ({ema21_val}) ➔ Kết luận: {ema_state}
- Độ lệch EMA: {ema_diff:.2f} USDT ➔ Đi ngang/Rối: {is_tangled}
- MACD: {indicators.get('macd', 'N/A')} (Signal: {indicators.get('macd_signal', 'N/A')})
- Biến động Volume: {indicators.get('volume_change', 'N/A')}
- Dự báo ML Model: {indicators.get('ml_signal', 'HOLD')}

LƯU Ý QUAN TRỌNG:
- Nếu {rsi_state} là 'DƯỚI 50 (BEARISH / SHORT)' và {ema_state} là 'EMA9 < EMA21 (GIẢM / SHORT)', điều kiện OPEN_SHORT ĐÃ HOÀN TOÀN THỎA MÃN. Không được kết luận ngược lại!
- Nếu {rsi_state} là 'TRÊN 50 (BULLISH)' và {ema_state} là 'EMA9 > EMA21 (TĂNG / LONG)', điều kiện OPEN_LONG ĐÃ HOÀN TOÀN THỎA MÃN.

Hãy đưa ra quyết định giao dịch dạng JSON (OPEN_LONG / OPEN_SHORT / CLOSE / HOLD).
"""
    return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 3. SUPERVISOR AGENT: Giám sát rủi ro & Phê duyệt lệnh (CHÂN PHANH)
# -------------------------------------------------------------
class SupervisorAgent:

  SYSTEM_PROMPT = """
    Bạn là Giám đốc Quản trị Rủi ro (Supervisor Agent).
    Nhiệm vụ: Phản biện và xét duyệt đề xuất từ Operator Agent dựa trên quy tắc an toàn vốn, CHỈ THỊ 1H và BÀI HỌC KINH NGHIỆM (MEMORY).

    Quy tắc kiểm duyệt (Strict Rules for Approval):
    1. Đề xuất HOLD hoặc CLOSE: Luôn DUYỆT (approved = true, risk_score = 1). CLOSE giúp cắt lỗ sớm hoặc chốt lời an toàn.
    2. Đề xuất OPEN_LONG:
       - TỪ CHỐI nếu Macro Directive là "ONLY_SHORT".
       - TỪ CHỐI nếu RSI > 75 (Quá mua - rủi ro đu đỉnh).
       - TỪ CHỐI nếu tài khoản đang giữ lệnh SHORT chưa đóng.
       - TỪ CHỐI nếu lặp lại sai lầm trong mục BÀI HỌC QUÁ KHỨ.
    3. Đề xuất OPEN_SHORT:
       - TỪ CHỐI nếu Macro Directive là "ONLY_LONG".
       - TỪ CHỐI nếu RSI < 25 (Quá bán - rủi ro bắt đáy short squeeze).
       - TỪ CHỐI nếu tài khoản đang giữ lệnh LONG chưa đóng.
       - TỪ CHỐI nếu lặp lại sai lầm trong mục BÀI HỌC QUÁ KHỨ.
    4. Độ tin cậy (confidence): DUYỆT nếu Operator có confidence >= 0.55 (Từ chối nếu < 0.55).

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
      macro_directive: str = "FLEXIBLE",
      past_lessons: list = None,
  ) -> dict:
    action = proposal.get("action")

    if action in ("HOLD", "CLOSE"):
      return {
          "approved": True,
          "risk_score": 1,
          "feedback": f"{action} không phát sinh rủi ro mở mới, tự động duyệt.",
      }

    if not position_info:
      position_info = {"side": "NONE"}
    if not past_lessons:
      past_lessons = ["Chưa có bài học rủi ro đặc biệt."]

    user_prompt = f"""
Đề xuất từ Operator: {json.dumps(proposal, ensure_ascii=False)}
Chỉ thị 1H từ Strategist: [{macro_directive}]
Vị thế hiện tại: {json.dumps(position_info, ensure_ascii=False)}
Chỉ số thị trường 5m: {json.dumps(indicators, ensure_ascii=False)}
Vốn khả dụng: {cash} USDT

BÀI HỌC KINH NGHIỆM TỪ CÁC LỆNH TRƯỚC:
{chr(10).join(['- ' + l for l in past_lessons[-3:]])}

Hãy thẩm định đề xuất này và trả về JSON.
"""
    return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 4. REFLECTOR AGENT: Đúc rút kinh nghiệm & TỰ TIẾN HÓA LUẬT
# -------------------------------------------------------------
class ReflectorAgent:

  SYSTEM_PROMPT = """
    You are a Senior Post-Mortem Trading Analyst (Reflector Agent).
    Analyze completed trades to extract ONE clear, actionable, concise takeaway in Vietnamese (max 20 words).

    JSON format:
    {
      "analysis": "Brief reason why trade succeeded or failed",
      "lesson": "Actionable takeaway for future trades in Vietnamese"
    }
    """

  SYSTEM_EVOLVE_PROMPT = """
    You are an AI Quantitative Strategy Optimizer.
    Your task is to analyze recent trade results (especially trades with early exits, premature stop-outs, or small profits) and REWRITE the strategy rules to improve profitability.
    Focus on fine-tuning 'exit_rules' (e.g., giving trades room to breathe, requiring clear EMA21 break before closing, minimum profit targets).

    CRITICAL: Output ONLY valid JSON in this exact structure:
    {
      "reason_for_update": "Lý do cập nhật luật bằng tiếng Việt ngắn gọn (dưới 25 từ)",
      "entry_rules": "Refined entry rules in Vietnamese or English",
      "exit_rules": "Refined exit rules in Vietnamese or English"
    }
    """

  def reflect(self, trade_summary: dict) -> str:
    user_prompt = f"""
DỮ LIỆU LỆNH VỪA ĐÓNG HOÀN TẤT:
- Vị thế: {trade_summary.get('side')}
- Giá vào: {trade_summary.get('entry_price')} ➔ Giá đóng: {trade_summary.get('exit_price')}
- PnL: {trade_summary.get('pnl_usdt'):+.4f} USDT ({trade_summary.get('pnl_pct'):+.2f}%)
- Lý do thoát: {trade_summary.get('exit_reason')}

Hãy đúc rút 1 câu bài học quan trọng nhất cho hệ thống.
"""
    result = _ask_llm(self.SYSTEM_PROMPT, user_prompt)
    lesson = result.get(
        "lesson",
        f"Lệnh {trade_summary.get('side')} PnL:"
        f" {trade_summary.get('pnl_pct'):+.2f}%",
    )
    self._save_to_memory(lesson, trade_summary)
    return lesson

  def auto_evolve_rules(self, recent_trades: list) -> dict:
    current_rules = self.load_rules()

    user_prompt = f"""
LỊCH SỬ CÁC LỆNH GẦN ĐÂY:
{json.dumps(recent_trades[-5:], ensure_ascii=False, indent=2)}

BỘ QUY TẮC HIỆN TẠI (v{current_rules.get('version', 1)}):
- Entry Rules: {current_rules.get('entry_rules')}
- Exit Rules: {current_rules.get('exit_rules')}

Nhiệm vụ: Nếu thấy bot đóng lệnh quá sớm (ăn non +0.03%, cắt lỗ oan khi giá chỉ hồi nhẹ chạm EMA9), hãy viết lại 'exit_rules' để bot có độ lỳ hơn, cho phép nến chạy trong sóng mạnh.
"""
    evolved = _ask_llm(self.SYSTEM_EVOLVE_PROMPT, user_prompt)

    if (
        "exit_rules" in evolved
        and "entry_rules" in evolved
        and "reason_for_update" in evolved
    ):
      new_rules = {
          "version": current_rules.get("version", 1) + 1,
          "last_updated": datetime.now(timezone.utc).isoformat(),
          "reason_for_update": evolved.get("reason_for_update"),
          "entry_rules": evolved.get("entry_rules"),
          "exit_rules": evolved.get("exit_rules"),
      }
      self._save_rules(new_rules)
      logging.info(
          ">>> [REFLECTOR TỰ NÂNG CẤP LUẬT] Phiên bản mới: v%d | Lý do: %s",
          new_rules["version"],
          new_rules["reason_for_update"],
      )
      return new_rules

    return current_rules

  def _save_to_memory(self, lesson: str, trade_summary: dict):
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if MEMORY_FILE.exists():
      try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
          history = json.load(f)
      except Exception:
        history = []

    history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pnl_pct": trade_summary.get("pnl_pct", 0.0),
        "lesson": lesson,
    })

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
      json.dump(history[-10:], f, ensure_ascii=False, indent=2)

  @staticmethod
  def load_lessons() -> list:
    if not MEMORY_FILE.exists():
      return []
    try:
      with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return [item.get("lesson", "") for item in data if "lesson" in item]
    except Exception:
      return []

  @staticmethod
  def load_rules() -> dict:
    if not RULES_FILE.exists():
      ReflectorAgent._save_rules(DEFAULT_RULES)
      return DEFAULT_RULES
    try:
      with open(RULES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return DEFAULT_RULES

  @staticmethod
  def _save_rules(rules: dict):
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
      json.dump(rules, f, ensure_ascii=False, indent=2)


# -------------------------------------------------------------
# 5. AUDITOR AGENT: Giám sát lỗi hệ thống & Đề xuất khắc phục
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
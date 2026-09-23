"""
Hệ thống Đa Tác Tử (Multi-Agent System) hỗ trợ chuyển đổi Local / Cloud.
1. StrategistAgent - Nhạc trưởng định hướng khung 1H
2. OperatorAgent   - Chân ga Scalping nến 5m
3. SupervisorAgent - Chân phanh duyệt lệnh & Phanh khẩn cấp tin tức
4. ReflectorAgent  - Đúc rút bài học vĩnh cửu & Tiến hóa phả hệ v1 -> vN
5. AuditorAgent    - SRE trực ban chẩn đoán sự cố (có inspect_error)
6. AgentTeam       - Đóng gói toàn bộ đội ngũ tương thích với main.py
"""

import os
import json
import time
import logging
import re
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, encoding="utf-8")

MEMORY_FILE = BASE_DIR / "storage" / "memory.json"
RULES_FILE = BASE_DIR / "storage" / "strategy_rules.json"

LLM_MODE = os.getenv("LLM_MODE", "LOCAL").upper()

# 1. Khởi tạo Client theo LLM_MODE
if LLM_MODE == "LOCAL":
    LOCAL_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    LOCAL_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:7b")
    LOCAL_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "ollama")
    local_client = OpenAI(api_key=LOCAL_API_KEY, base_url=LOCAL_BASE_URL, timeout=45.0)
    cloud_gemini_client = None
    cloud_groq_client = None
else:
    local_client = None
    cloud_gemini_client = OpenAI(
        api_key=os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY", ""),
        base_url=os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
        timeout=30.0
    )
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    cloud_groq_client = (
        OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1", timeout=15.0)
        if os.getenv("GROQ_API_KEY") else None
    )
    GROQ_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "qwen/qwen3.8-27b")

DEFAULT_RULES = {
    "version": 1,
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "reason_for_update": "Bộ quy tắc khởi tạo mặc định cho Scalping 5m",
    "entry_rules": "OPEN_LONG khi EMA9 > EMA21 và RSI > 50 (tuân thủ chỉ thị 1H). OPEN_SHORT khi EMA9 < EMA21 và RSI < 50 (tuân thủ chỉ thị 1H).",
    "exit_rules": "Giữ lệnh HOLD trong xu hướng. CHỈ ĐÓNG khi nến đóng gãy EMA21 và RSI xác nhận đảo chiều.",
    "evolution_history": []
}


def _extract_json(text: str) -> dict:
    text = text.strip()
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    clean_text = json_match.group(1) if json_match else text
    try:
        return json.loads(clean_text)
    except Exception:
        start = clean_text.find("{")
        end = clean_text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(clean_text[start:end + 1])
        raise


def _ask_llm(system_prompt: str, user_prompt: str) -> dict:
    """Hàm gọi LLM dùng chung cho toàn bộ Agent (kể cả SentimentAgent)."""
    time.sleep(0.3)
    if LLM_MODE == "LOCAL":
        try:
            res = local_client.chat.completions.create(
                model=LOCAL_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
            )
            return _extract_json(res.choices[0].message.content)
        except Exception as e:
            logging.error(f"Lỗi gọi Local LLM ({LOCAL_MODEL}): {e}")
            return {"error": str(e), "sentiment": "NEUTRAL", "panic_score": 5, "trading_advice": "NORMAL", "key_driver": "Local LLM Error"}

    # Chế độ Cloud (Gemini + Groq failover)
    try:
        res = cloud_gemini_client.chat.completions.create(
            model=GEMINI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=300
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        logging.warning(f"⚠️ Google Gemini gặp sự cố: {str(e)[:70]}")

    if cloud_groq_client:
        try:
            logging.info(f">>> [FAILOVER CỨU HỘ] Đang chuyển sang Groq ({GROQ_MODEL})...")
            res = cloud_groq_client.chat.completions.create(
                model=GROQ_MODEL,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=300
            )
            return json.loads(res.choices[0].message.content)
        except Exception as ge:
            logging.error(f"Lỗi cả Groq cứu hộ: {ge}")

    return {"error": "Tat ca LLM Cloud deu gap su co", "sentiment": "NEUTRAL", "panic_score": 5, "trading_advice": "NORMAL", "key_driver": "Cloud Error"}


# -------------------------------------------------------------
# 1. STRATEGIST AGENT (1H)
# -------------------------------------------------------------
class StrategistAgent:
    SYSTEM_PROMPT = """
    You are the Senior Chief Strategist for a Crypto Quantitative Fund.
    Analyze the 1-HOUR (1H) MACRO TREND. Dictate whether 5m Scalper is allowed to go LONG, SHORT, or BOTH.
    RULES:
    - "ONLY_LONG" : 1H Price > EMA50, EMA50 > EMA200, RSI_1H > 52.
    - "ONLY_SHORT": 1H Price < EMA50, EMA50 < EMA200, RSI_1H < 48.
    - "FLEXIBLE"  : Market is in 1H consolidation.
    JSON format:
    { "macro_bias": "BULLISH" | "BEARISH" | "SIDEWAY", "directive": "ONLY_LONG" | "ONLY_SHORT" | "FLEXIBLE", "reasoning": "Brief explanation" }
    """

    def __init__(self, config=None):
        self.config = config

    def analyze_macro(self, symbol: str, current_price: float, h1_ind: dict) -> dict:
        user_prompt = f"""
Thị trường: {symbol} | Giá: {current_price} USDT
DỮ LIỆU 1H: RSI(14)={h1_ind.get('rsi_14', 'N/A')}, EMA50={h1_ind.get('ema_50', 'N/A')}, EMA200={h1_ind.get('ema_200', 'N/A')}.
Vị trí giá: {'TRÊN' if current_price >= h1_ind.get('ema_50', current_price) else 'DƯỚI'} EMA50 1H.
Ban hành chỉ thị xu hướng 1H dạng JSON.
"""
        return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 2. OPERATOR AGENT (5m)
# -------------------------------------------------------------
class OperatorAgent:
    SYSTEM_PROMPT = """
    You are an Aggressive Scalping Trader on the 5m crypto timeframe.
    Follow strictly the DYNAMIC STRATEGY RULES provided in the prompt.
    Output ONLY valid JSON:
    { "action": "OPEN_LONG" | "OPEN_SHORT" | "CLOSE" | "HOLD", "confidence": 0.60 to 0.95, "reason": "Direct technical trigger" }
    """

    def __init__(self, config=None):
        self.config = config

    def analyze(self, symbol: str, current_price: float, indicators: dict, position_info: dict = None, macro_directive: str = "FLEXIBLE") -> dict:
        if not position_info:
            position_info = {"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0}

        rules = ReflectorAgent.load_rules()
        rsi_val = float(indicators.get("rsi_14", 50))
        ema9_val = float(indicators.get("ema_9", current_price))
        ema21_val = float(indicators.get("ema_21", current_price))

        rsi_state = "TRÊN 50 (BULLISH)" if rsi_val > 50 else "DƯỚI 50 (BEARISH)"
        ema_state = "EMA9 > EMA21 (TĂNG)" if ema9_val > ema21_val else "EMA9 < EMA21 (GIẢM)"

        user_prompt = f"""
Thị trường: {symbol} | Giá: {current_price} USDT | Chỉ thị 1H: [{macro_directive}]
BỘ QUY TẮC HIỆN HÀNH (v{rules.get('version', 1)}):
- Entry Rules: {rules.get('entry_rules')}
- Exit Rules: {rules.get('exit_rules')}
Vị thế: {position_info.get('side', 'NONE')} (PnL: {position_info.get('pnl_pct', 0.0):.2f}%)
Kỹ thuật: RSI={rsi_val} ({rsi_state}), EMA9={ema9_val} vs EMA21={ema21_val} ({ema_state}).
Hãy đưa ra quyết định dạng JSON (OPEN_LONG / OPEN_SHORT / CLOSE / HOLD).
"""
        return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 3. SUPERVISOR AGENT (Kiểm duyệt rủi ro)
# -------------------------------------------------------------
class SupervisorAgent:
    SYSTEM_PROMPT = """
    Bạn là Giám đốc Quản trị Rủi ro (Supervisor Agent).
    Phản biện đề xuất từ Operator Agent dựa trên an toàn vốn, CHỈ THỊ 1H, BÀI HỌC KINH NGHIỆM và TÌNH BÁO SENTIMENT.
    QUY TẮC KIỂM DUYỆT:
    1. HOLD/CLOSE: Luôn DUYỆT (approved = true, risk_score = 1).
    2. OPEN_LONG/SHORT:
       - TỪ CHỐI nếu black_swan_alert = true hoặc panic_score >= 8 hoặc trading_advice == "HALT_TRADING".
       - TỪ CHỐI nếu Macro 1H xung đột (chỉ thị ONLY_SHORT cấm mở Long; ONLY_LONG cấm mở Short).
       - TỪ CHỐI nếu lặp lại sai lầm trong BÀI HỌC KINH NGHIỆM.
    JSON format:
    { "approved": true | false, "risk_score": 1 to 10, "feedback": "Lý do duyệt hoặc từ chối" }
    """

    def __init__(self, config=None):
        self.config = config

    def review(self, proposal: dict, indicators: dict, cash: float, position_info: dict = None, macro_directive: str = "FLEXIBLE", past_lessons: list = None, sentiment_info: dict = None) -> dict:
        action = proposal.get("action", "HOLD")

        if action in ("HOLD", "CLOSE"):
            return {"approved": True, "risk_score": 1, "feedback": f"{action} tự động duyệt."}

        if sentiment_info and (sentiment_info.get("black_swan_alert") or sentiment_info.get("panic_score", 0) >= 8 or sentiment_info.get("trading_advice") == "HALT_TRADING"):
            driver = sentiment_info.get("key_driver", "Rủi ro tin tức cực đoan")
            return {"approved": False, "risk_score": 10, "feedback": f"PHANH KHẨN CẤP: Từ chối {action} do rủi ro tin tức: {driver}"}

        if not position_info:
            position_info = {"side": "NONE"}
        if not past_lessons:
            past_lessons = ["Không có cảnh báo đặc biệt."]
        if not sentiment_info:
            sentiment_info = {"sentiment": "NEUTRAL", "panic_score": 5, "key_driver": "Bình thường"}

        lessons_str = "\n".join([f"- {l}" for l in past_lessons])

        user_prompt = f"""
Đề xuất: {json.dumps(proposal, ensure_ascii=False)} | Chỉ thị 1H: [{macro_directive}]
Vị thế hiện tại: {json.dumps(position_info, ensure_ascii=False)} | Vốn: {cash} USDT
Tình báo Tin tức: Tâm lý [{sentiment_info.get('sentiment')}], Điểm hoảng loạn [{sentiment_info.get('panic_score')}/10], Tin: {sentiment_info.get('key_driver')}
BÀI HỌC KINH NGHIỆM ĐÃ LỌC:
{lessons_str}
Thẩm định đề xuất và trả về JSON.
"""
        return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 4. REFLECTOR AGENT (Lifelong Learning)
# -------------------------------------------------------------
class ReflectorAgent:
    SYSTEM_PROMPT = """
    You are a Senior Trading Analyst. Extract ONE concise actionable takeaway in Vietnamese (max 20 words).
    JSON format: { "analysis": "Reason for result", "lesson": "Takeaway in Vietnamese" }
    """

    SYSTEM_EVOLVE_PROMPT = """
    You are an AI Quantitative Strategy Optimizer managing a lifelong evolutionary strategy tree.
    Analyze recent trades alongside the FULL HISTORICAL EVOLUTION TREE (v1 -> vN).
    CRITICAL: Never regress into flaws already resolved in prior versions.
    JSON format:
    {
      "reason_for_update": "Lý do nâng cấp bộ luật ngắn gọn",
      "flaw_identified": "Điểm yếu cốt lõi của phiên bản cũ",
      "entry_rules": "Bộ quy tắc vào lệnh hoàn chỉnh",
      "exit_rules": "Bộ quy tắc thoát lệnh hoàn chỉnh"
    }
    """

    def __init__(self, config=None):
        self.config = config

    def reflect(self, trade_summary: dict) -> str:
        user_prompt = f"""
LỆNH VỪA ĐÓNG: Vị thế {trade_summary.get('side')} | Giá vào: {trade_summary.get('entry_price')} ➔ Giá đóng: {trade_summary.get('exit_price')}
PnL: {trade_summary.get('pnl_usdt'):+.4f} USDT ({trade_summary.get('pnl_pct'):+.2f}%) | Lý do: {trade_summary.get('exit_reason')}
Hãy đúc rút 1 câu bài học quan trọng nhất cho hệ thống.
"""
        res = _ask_llm(self.SYSTEM_PROMPT, user_prompt)
        lesson = res.get("lesson", f"Lệnh {trade_summary.get('side')} PnL: {trade_summary.get('pnl_pct'):+.2f}%")
        self._save_to_memory(lesson, trade_summary)
        return lesson

    def auto_evolve_rules(self, recent_trades: list) -> dict:
        current_data = self.load_full_registry()
        current_ver = current_data.get("version", 1)
        history = current_data.get("evolution_history", [])

        history_summary = [f"- v{h.get('version', '?')}: {h.get('reason', 'N/A')} | Sửa lỗi: {h.get('flaw_identified', 'N/A')}" for h in history]
        history_str = "\n".join(history_summary) if history_summary else "Chưa có phả hệ cũ."

        user_prompt = f"""
LỊCH SỬ TIẾN HÓA V1 -> V{current_ver}:
{history_str}
BỘ QUY TẮC HIỆN TẠI (v{current_ver}):
- Lý do: {current_data.get('reason_for_update')}
- Entry: {current_data.get('entry_rules')}
- Exit: {current_data.get('exit_rules')}
CÁC LỆNH GẦN ĐÂY:
{json.dumps(recent_trades[-5:], ensure_ascii=False, indent=2)}
Viết tiếp phiên bản v{current_ver + 1}, tuyệt đối không lặp lại lỗi đã sửa ở các version trước.
"""
        evolved = _ask_llm(self.SYSTEM_EVOLVE_PROMPT, user_prompt)

        if isinstance(evolved, dict) and "exit_rules" in evolved and "entry_rules" in evolved:
            new_version = current_ver + 1
            history.append({
                "version": current_ver,
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "reason": current_data.get("reason_for_update", "N/A"),
                "flaw_identified": evolved.get("flaw_identified", "Cần tối ưu thêm hiệu suất"),
                "entry_rules": current_data.get("entry_rules"),
                "exit_rules": current_data.get("exit_rules")
            })
            new_rules = {
                "version": new_version,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "reason_for_update": evolved.get("reason_for_update", f"Nâng cấp lên v{new_version}"),
                "entry_rules": evolved.get("entry_rules"),
                "exit_rules": evolved.get("exit_rules"),
                "evolution_history": history
            }
            self._save_rules(new_rules)
            logging.info(f">>> [TIẾN HÓA] Đã nâng cấp lên v{new_version}: {new_rules['reason_for_update']}")
            return new_rules
        return current_data

    @classmethod
    def load_full_registry(cls) -> dict:
        if not RULES_FILE.exists():
            cls._save_rules(DEFAULT_RULES)
            return DEFAULT_RULES
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "evolution_history" not in data:
                    data["evolution_history"] = []
                return data
        except Exception:
            return DEFAULT_RULES

    @classmethod
    def load_rules(cls) -> dict:
        return cls.load_full_registry()

    @staticmethod
    def _save_rules(rules: dict):
        RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)

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
            "id": len(history) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "side": trade_summary.get("side", "NONE"),
            "pnl_pct": trade_summary.get("pnl_pct", 0.0),
            "exit_reason": trade_summary.get("exit_reason", "MANUAL"),
            "lesson": lesson
        })

        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_lessons(side: str = None) -> list:
        if not MEMORY_FILE.exists():
            return []
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not data:
                return []

            if len(data) <= 20:
                return [f"[#{item.get('id', i+1)}] {item.get('lesson', '')}" for i, item in enumerate(data) if "lesson" in item]

            loss_trades = sorted([d for d in data if d.get("pnl_pct", 0) < 0], key=lambda x: x.get("pnl_pct", 0))
            critical_lessons = [f"[CẢNH BÁO LỖ #{d.get('id')} ({d.get('pnl_pct'):.2f}%)] {d.get('lesson')}" for d in loss_trades[:10]]

            relevant_recent = [d for d in data if side is None or d.get("side") == side or d.get("side") == "NONE"][-15:]
            recent_lessons = [f"[GẦN ĐÂY #{d.get('id')}] {d.get('lesson')}" for d in relevant_recent]

            return list(dict.fromkeys(critical_lessons + recent_lessons))
        except Exception:
            return []


# -------------------------------------------------------------
# 5. AUDITOR AGENT (SRE)
# -------------------------------------------------------------
class AuditorAgent:
    SYSTEM_PROMPT = """
    Bạn là Kỹ sư SRE giám sát Trading Bot. Đọc traceback log để chẩn đoán nguyên nhân.
    JSON format: { "severity": "WARNING" | "CRITICAL", "diagnosis": "Giải thích ngắn gọn", "suggested_action": "Hành động bot nên làm" }
    """

    def __init__(self, config=None):
        self.config = config

    def inspect_error(self, traceback_str: str) -> dict:
        """Chẩn đoán lỗi khi bot gặp ngoại lệ bất thường."""
        user_prompt = f"Lỗi hệ thống:\n{traceback_str}\nPhân tích và trả về JSON."
        return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 6. AGENT TEAM (Đóng gói 6 Agent)
# -------------------------------------------------------------
class AgentTeam:
    def __init__(self, config=None):
        self.config = config
        self.strategist = StrategistAgent(config)
        self.operator = OperatorAgent(config)
        self.supervisor = SupervisorAgent(config)
        self.reflector = ReflectorAgent(config)
        self.auditor = AuditorAgent(config)

        # Import trễ tránh circular import
        from agents.sentiment_agent import SentimentAgent
        self.sentiment = SentimentAgent(config)

        # Định danh tương thích
        self.strategist_agent = self.strategist
        self.operator_agent = self.operator
        self.supervisor_agent = self.supervisor
        self.reflector_agent = self.reflector
        self.auditor_agent = self.auditor
        self.sentiment_agent = self.sentiment
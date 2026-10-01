"""
Hệ thống Đa Tác Tử (Multi-Agent System) hỗ trợ:
1. Chuỗi Fallback 3 Tầng Tự Động:
   - Tier 1: Google Gemini 3.1 Flash Lite (Chính - Rẻ, quota lớn gánh 3.000+ token)
   - Tier 2: Ollama Cloud gemma4:31b-cloud (Dự phòng 1 - Logic toán học chính xác)
   - Tier 3: Groq Cloud qwen/qwen3.8-27b (Chốt chặn an toàn siêu tốc 0.3s)
2. Tự động học hỏi (Lifelong Learning) và tự động tiến hóa phả hệ bộ luật (v1 -> vN) 24/7
3. Đồng bộ hóa Machine Learning (model.pkl) trực tiếp vào logic ra quyết định của Operator
4. ĐÃ VÁ LỖI TOÀN DIỆN:
   - Triệt tiêu lỗi tiến hóa vô tận sau mỗi lệnh giao dịch (chuẩn hóa theo trade_id).
   - Khóa nhận thức LLM: Ngăn LLM ảo tưởng sửa code cơ học Python EMA21.
   - Dập tắt toàn bộ cảnh báo UserWarning sklearn trên Python 3.14.
   - Sửa hàm gửi Discord bằng requests, chống lỗi 400 Bad Request khi payload quá dài.
   - Chặn bẫy phí sàn nuốt lãi li ti kích hoạt tiến hóa liên tục.
"""

# 1. Dập tắt cảnh báo Scikit-Learn / Joblib trên Python 3.14 ngay đầu file
import warnings
warnings.filterwarnings("ignore")

import os
import json
import time
import logging
import re
import pickle
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
import numpy as np
import pandas as pd
import requests
from openai import OpenAI

# Hỗ trợ bộ nạp Scikit-Learn Joblib
try:
    import joblib
except ImportError:
    joblib = None

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, encoding="utf-8")

MEMORY_FILE = BASE_DIR / "storage" / "memory.json"
RULES_FILE = BASE_DIR / "storage" / "strategy_rules.json"
MODEL_PATH = BASE_DIR / "models" / "model.pkl"

logger = logging.getLogger("CryptoAI")

# -------------------------------------------------------------
# KHỞI TẠO ĐỒNG THỜI CẢ 3 TẦNG KẾT NỐI (SẴN SÀNG CHO CHUỖI DỰ PHÒNG)
# -------------------------------------------------------------

# 1. TẦNG 1: GOOGLE GEMINI (FLASH LITE)
cloud_gemini_client = None
gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
if gemini_key:
    cloud_gemini_client = OpenAI(
        api_key=gemini_key,
        base_url=os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
        timeout=15.0
    )
GEMINI_MODEL = os.getenv("LLM_MODEL_NAME", "gemini-3.1-flash-lite")

# 2. TẦNG 2: OLLAMA CLOUD (GEMMA 4 31B CLOUD)
local_client = None
local_base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
if local_base_url:
    local_client = OpenAI(
        api_key=os.getenv("LOCAL_LLM_API_KEY", "ollama"),
        base_url=local_base_url,
        timeout=30.0
    )
LOCAL_MODEL = os.getenv("LOCAL_LLM_MODEL", "gemma4:31b-cloud")

# 3. TẦNG 3: GROQ CLOUD (CHỐT CHẶN CUỐI)
groq_client = None
if os.getenv("GROQ_API_KEY"):
    groq_client = OpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
        timeout=12.0
    )
GROQ_MODEL = os.getenv("GROQ_MODEL") or os.getenv("GROQ_FALLBACK_MODEL", "qwen/qwen3.8-27b")

DEFAULT_RULES = {
    "version": 1,
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "reason_for_update": "Khởi tạo bộ quy tắc chuẩn kỹ thuật Scalping 5m với quyền thoát lệnh linh hoạt.",
    "entry_rules": "1. TREND MODE (70% vốn): Khung 1H đồng thuận + EMA9/EMA21 xác nhận + RSI 5m > 55 (Long) hoặc < 45 (Short). 2. FLEXIBLE MODE (30% vốn): RSI 5m thoát vùng nhiễu 45-55 VÀ nến 5m đóng cửa vượt qua EMA9. Cấm vào lệnh khi khoảng cách EMA9/EMA21 < 0.05%.",
    "exit_rules": "1. Hard Stop-Loss cơ học tại -1.2%. 2. Chốt lời chủ động khi RSI 5m > 70 (với Long) hoặc < 30 (với Short) khi có lãi. 3. Operator đề xuất CLOSE ngay khi nến 5m đóng cửa vi phạm EMA21 hoặc khi chỉ thị 1H đảo chiều ngược vị thế.",
    "evolution_history": []
}


def _send_discord_alert(title: str, description: str, color: int = 0x9B59B6):
    """Bắn thông báo tiến hóa qua Discord Webhook bằng requests, chống lỗi 400 payload."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return
    try:
        safe_desc = description[:1800] if len(description) > 1800 else description
        payload = {
            "embeds": [
                {
                    "title": title[:250],
                    "description": safe_desc,
                    "color": color,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            ]
        }
        res = requests.post(webhook_url, json=payload, timeout=5)
        if res.status_code not in (200, 204):
            logger.warning(f"Discord Webhook phản hồi mã: {res.status_code} - {res.text}")
    except Exception as e:
        logger.warning(f"Không thể gửi thông báo Discord: {e}")


def _extract_json(text: str) -> dict:
    """Trích xuất JSON an toàn từ phản hồi văn bản của LLM, chống lỗi Markdown fences."""
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
    """Cơ chế điều phối gọi LLM 3 tầng tự động Fallback."""
    time.sleep(0.1)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # Tier 1: Gemini
    if cloud_gemini_client:
        try:
            res = cloud_gemini_client.chat.completions.create(
                model=GEMINI_MODEL,
                response_format={"type": "json_object"},
                messages=messages,
                temperature=0.1,
                max_tokens=5000
            )
            return _extract_json(res.choices[0].message.content)
        except Exception as e:
            logger.warning(f"⚠️ [Tier 1 - Gemini] Lỗi/Timeout: {str(e)[:80]} ➔ Chuyển sang Tier 2...")

    # Tier 2: Ollama Cloud
    if local_client:
        try:
            res = local_client.chat.completions.create(
                model=LOCAL_MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=5000
            )
            logger.info("🛡️ [Tier 2 - Gemma 4 Cloud] Đã phản hồi thay thế thành công!")
            return _extract_json(res.choices[0].message.content)
        except Exception as e:
            logger.warning(f"⚠️ [Tier 2 - Gemma 4 Cloud] Lỗi/Timeout: {str(e)[:80]} ➔ Chuyển sang Tier 3...")

    # Tier 3: Groq Cloud
    if groq_client:
        try:
            res = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                response_format={"type": "json_object"},
                messages=messages,
                temperature=0.1,
                max_tokens=5000
            )
            logger.info("⚡ [Tier 3 - Groq Cloud] Chốt chặn cuối cùng đã phản hồi thành công!")
            return _extract_json(res.choices[0].message.content)
        except Exception as e:
            logger.error(f"❌ [TẤT CẢ 3 TẦNG ĐỀU THẤT BẠI]: {e}")

    return {
        "action": "HOLD",
        "confidence": 0.5,
        "reason": "Mất kết nối toàn bộ 3 tầng LLM - Kích hoạt HOLD an toàn",
        "approved": True,
        "risk_score": 1,
        "feedback": "HOLD tự động bảo vệ vốn.",
        "directive": "FLEXIBLE",
        "macro_bias": "SIDEWAY",
        "sentiment": "NEUTRAL",
        "panic_score": 3,
        "key_driver": "3-Tier Offline Shield"
    }


# -------------------------------------------------------------
# 1. STRATEGIST AGENT (1H)
# -------------------------------------------------------------
class StrategistAgent:
    SYSTEM_PROMPT = """
    You are the Senior Chief Strategist for a Crypto Quantitative Fund.
    Analyze the 1-HOUR (1H) MACRO TREND to dictate 5m Scalper behavior:

    CRITICAL RULES:
    - "ONLY_LONG" : 1H Price > EMA50 AND RSI_1H > 52. (Bullish Momentum - Longs allowed).
    - "ONLY_SHORT": 1H Price < EMA50 AND RSI_1H < 48. (Bearish Breakdown - Allow immediate Shorting).
    - "FLEXIBLE"  : ONLY when 1H Price is hovering tightly around EMA50 (+-0.2%) OR RSI_1H is in the neutral zone (48 to 52).

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
Quy tắc: Nếu Giá < EMA50 và RSI < 48, BẮT BUỘC chỉ thị là ONLY_SHORT để mở đường cho phe Bán.
Ban hành chỉ thị xu hướng 1H dạng JSON.
"""
        return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 2. OPERATOR AGENT (5m - Tích hợp ML Engine chuẩn & Thoát lệnh linh hoạt)
# -------------------------------------------------------------
class OperatorAgent:
    SYSTEM_PROMPT = """
    You are an Aggressive Scalping Trader on the 5m crypto timeframe.
    You strictly combine technical indicators (EMA, RSI), DYNAMIC STRATEGY RULES, and MACHINE LEARNING (Random Forest) probability.
    
    ACTION DECISION GUIDELINES:
    1. ENTRY LONG: ML BUY Probability > 65%, EMA9 > EMA21, RSI > 55, and 1H allows Long.
    2. ENTRY SHORT: ML BUY Probability < 35%, EMA9 < EMA21, RSI < 45, and 1H allows Short.
    3. EXIT / CLOSE RULES (MANDATORY TACTICAL EXITS):
       - If currently in LONG and: 1H directive flips to ONLY_SHORT, OR 5m EMA9 crosses below EMA21, OR RSI crosses above 70 with profit -> Propose "CLOSE".
       - If currently in SHORT and: 1H directive flips to ONLY_LONG, OR 5m EMA9 crosses above EMA21, OR RSI drops below 30 with profit -> Propose "CLOSE".
       - Do not hold blindly when technical momentum reverses against the position!
    4. HOLD: Only maintain position when trend structure remains aligned with trade direction.
    
    Output ONLY valid JSON:
    { "action": "OPEN_LONG" | "OPEN_SHORT" | "CLOSE" | "HOLD", "confidence": 0.60 to 0.95, "reason": "Direct technical trigger + ML probability context" }
    """

    def __init__(self, config=None):
        self.config = config
        self.model = None
        self.load_ml_model()

    def load_ml_model(self):
        """Nạp file model.pkl vào bộ nhớ RAM (Hỗ trợ cả Joblib và Pickle)."""
        if not MODEL_PATH.exists():
            self.model = None
            return

        if joblib is not None:
            try:
                self.model = joblib.load(MODEL_PATH)
                logger.info("🤖 [OPERATOR] Đã nạp thành công mô hình ML bằng joblib (model.pkl)")
                return
            except Exception:
                pass

        try:
            with open(MODEL_PATH, "rb") as f:
                self.model = pickle.load(f)
            logger.info("🤖 [OPERATOR] Đã nạp thành công mô hình ML bằng pickle (model.pkl)")
            return
        except Exception as e:
            logger.warning(f"Không thể nạp model.pkl: {e}")
            self.model = None

    def reload_model(self):
        """Hot-Swap: Tải lại model mới vào RAM."""
        logger.info("🔄 [HOT-SWAP] OperatorAgent đang nạp mô hình vừa được tái huấn luyện...")
        self.load_ml_model()

    def predict_ml_probability(self, indicators: dict) -> float:
        """Dự đoán xác suất TĂNG GIÁ (BUY) từ mô hình Random Forest."""
        if not self.model:
            return 0.5

        try:
            price = float(indicators.get("price", 1.0))
            ema9 = float(indicators.get("ema_9", price))
            ema21 = float(indicators.get("ema_21", price))
            rsi14 = float(indicators.get("rsi_14", 50.0))
            macd = float(indicators.get("macd", ema9 - ema21))
            spread_pct = ((ema9 - ema21) / price) * 100.0

            feature_pool = {
                "rsi_14": rsi14,
                "macd": macd,
                "macd_signal": float(indicators.get("macd_signal", 0.0)),
                "ema_9": ema9,
                "ema_21": ema21,
                "ema_spread_pct": spread_pct,
                "ema_spread": spread_pct,
                "volume_change": float(indicators.get("volume_change", 0.0)),
                "vol_ratio": 1.0
            }

            if hasattr(self.model, "feature_names_in_"):
                expected_cols = list(self.model.feature_names_in_)
                row = [feature_pool.get(col, 0.0) for col in expected_cols]
                X = pd.DataFrame([row], columns=expected_cols)
            else:
                default_cols = ["rsi_14", "macd", "macd_signal", "ema_9", "ema_21", "ema_spread_pct", "volume_change"]
                row = [feature_pool.get(col, 0.0) for col in default_cols]
                X = pd.DataFrame([row], columns=default_cols)

            probabilities = self.model.predict_proba(X)[0]
            classes = list(getattr(self.model, "classes_", []))

            if "BUY" in classes:
                buy_idx = classes.index("BUY")
            elif 1 in classes:
                buy_idx = classes.index(1)
            elif "1" in classes:
                buy_idx = classes.index("1")
            else:
                buy_idx = 0

            prob_buy = float(probabilities[buy_idx])
            return round(prob_buy, 4)

        except Exception as e:
            logger.warning(f"Lỗi suy luận ML: {e}")
            return 0.5

    def analyze(self, symbol: str, current_price: float, indicators: dict, position_info: dict = None, macro_directive: str = "FLEXIBLE") -> dict:
        if not position_info:
            position_info = {"side": "NONE", "entry_price": 0.0, "pnl_pct": 0.0, "holding_candles": 0}

        rules = ReflectorAgent.load_rules()
        rsi_val = float(indicators.get("rsi_14", 50))
        ema9_val = float(indicators.get("ema_9", current_price))
        ema21_val = float(indicators.get("ema_21", current_price))

        rsi_state = "TRÊN 50 (BULLISH)" if rsi_val > 50 else "DƯỚI 50 (BEARISH)"
        ema_state = "EMA9 > EMA21 (TĂNG)" if ema9_val > ema21_val else "EMA9 < EMA21 (GIẢM)"

        ml_prob = self.predict_ml_probability(indicators)
        ml_bias = "BULLISH (TĂNG)" if ml_prob > 0.55 else ("BEARISH (GIẢM)" if ml_prob < 0.45 else "NEUTRAL (ĐI NGANG)")

        user_prompt = f"""
Thị trường: {symbol} | Giá: {current_price} USDT | Chỉ thị 1H: [{macro_directive}]
BỘ QUY TẮC HIỆN HÀNH (v{rules.get('version', 1)}):
- Entry Rules: {rules.get('entry_rules')}
- Exit Rules: {rules.get('exit_rules')}

VỊ THẾ HIỆN TẠI:
- Hướng vị thế: {position_info.get('side', 'NONE')}
- Giá vào: {position_info.get('entry_price', 0.0)} | PnL: {position_info.get('pnl_pct', 0.0):.2f}% | Số nến nắm giữ: {position_info.get('holding_candles', 0)}

TÍN HIỆU KỸ THUẬT 5M:
- RSI(14): {rsi_val} ({rsi_state})
- EMA9 vs EMA21: {ema9_val} vs {ema21_val} ({ema_state})
- ML BUY Probability: {ml_prob:.1%} [{ml_bias}]

YÊU CẦU RA QUYẾT ĐỊNH:
- Nếu đang giữ vị thế mà chỉ báo đảo chiều ngược chiều vị thế hoặc chạm ngưỡng chốt lời: Hãy đề xuất CLOSE.
- Nếu không có vị thế: Phân tích mở OPEN_LONG, OPEN_SHORT hoặc HOLD.

Hãy đưa ra quyết định dạng JSON (OPEN_LONG / OPEN_SHORT / CLOSE / HOLD).
"""
        return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 3. SUPERVISOR AGENT
# -------------------------------------------------------------
class SupervisorAgent:
    SYSTEM_PROMPT = """
    Bạn là Giám đốc Quản trị Rủi ro (Supervisor Agent) của quỹ Scalping Crypto.
    Nhiệm vụ: Phản biện đề xuất từ Operator Agent dựa trên an toàn vốn, CHỈ THỊ 1H và BÀI HỌC KINH NGHIỆM.

    QUY TẮC THÉP:
    1. HOLD và CLOSE: LUÔN DUYỆT NGAY LẬP TỨC (approved = true, risk_score = 1). Tuyệt đối không dùng tin tức để ngăn cản việc đóng lệnh bảo toàn vốn!
    2. VỀ PHANH KHẨN CẤP TIN TỨC:
       - Chỉ phanh khẩn cấp đối với lệnh MỞ MỚI (OPEN_LONG / OPEN_SHORT) khi: black_swan_alert = true hoặc panic_score >= 7 hoặc trading_advice == "HALT_TRADING".
       - Lệnh CLOSE KHÔNG BAO GIỜ bị phanh khẩn cấp chặn lại!
    3. ĐÍNH CHÍNH LỆNH SHORT THUẬN XU HƯỚNG:
       - Mở SHORT khi EMA9 < EMA21 và RSI < 45 là THUẬN XU HƯỚNG GIẢM. Bắt buộc duyệt nếu chỉ thị 1H cho phép.

    JSON format:
    { "approved": true | false, "risk_score": 1 to 10, "feedback": "Lập luận phản biện rõ ràng" }
    """

    def __init__(self, config=None):
        self.config = config

    def review(self, proposal: dict, indicators: dict, cash: float, position_info: dict = None, macro_directive: str = "FLEXIBLE", past_lessons: list = None, sentiment_info: dict = None) -> dict:
        action = proposal.get("action", "HOLD")

        if action in ("HOLD", "CLOSE"):
            return {"approved": True, "risk_score": 1, "feedback": f"{action} tự động duyệt bảo toàn vốn."}

        if sentiment_info and (sentiment_info.get("black_swan_alert") or sentiment_info.get("panic_score", 0) >= 7 or sentiment_info.get("trading_advice") == "HALT_TRADING"):
            driver = sentiment_info.get("key_driver", "Rủi ro tin tức cực đoan")
            return {"approved": False, "risk_score": 10, "feedback": f"PHANH KHẨN CẤP: Từ chối {action} do rủi ro tin tức: {driver}"}

        if macro_directive == "ONLY_SHORT" and action == "OPEN_LONG":
            return {"approved": False, "risk_score": 9, "feedback": "Từ chối OPEN_LONG vì chỉ thị 1H là ONLY_SHORT."}
        if macro_directive == "ONLY_LONG" and action == "OPEN_SHORT":
            return {"approved": False, "risk_score": 9, "feedback": "Từ chối OPEN_SHORT vì chỉ thị 1H là ONLY_LONG."}

        if not position_info:
            position_info = {"side": "NONE"}
        if not past_lessons:
            past_lessons = ["Không có cảnh báo đặc biệt."]
        if not sentiment_info:
            sentiment_info = {"sentiment": "NEUTRAL", "panic_score": 3, "key_driver": "Bình thường"}

        lessons_str = "\n".join([f"- {l}" for l in past_lessons])

        user_prompt = f"""
Đề xuất từ Operator: {json.dumps(proposal, ensure_ascii=False)} | Chỉ thị 1H: [{macro_directive}]
Vị thế hiện tại: {json.dumps(position_info, ensure_ascii=False)} | Vốn khả dụng: {cash} USDT
Kỹ thuật 5m: RSI={indicators.get('rsi_14')}, EMA9={indicators.get('ema_9')}, EMA21={indicators.get('ema_21')}
Tình báo Tin tức: Tâm lý [{sentiment_info.get('sentiment')}], Điểm hoảng loạn [{sentiment_info.get('panic_score')}/10], Tin: {sentiment_info.get('key_driver')}
BÀI HỌC KINH NGHIỆM ĐÃ LỌC:
{lessons_str}

LƯU Ý DUYỆT LỆNH:
- Điểm hoảng loạn tin tức là {sentiment_info.get('panic_score')}/10 (< 7): Không dùng tâm lý báo chí để chặn đề xuất mở lệnh kỹ thuật hợp lệ.
- Mở SHORT khi EMA9 < EMA21 và RSI < 45 là đánh thuận xu hướng giảm. Bắt buộc duyệt nếu đúng xu hướng!
Thẩm định và trả về JSON.
"""
        review_res = _ask_llm(self.SYSTEM_PROMPT, user_prompt)

        if action == "OPEN_SHORT" and not review_res.get("approved"):
            feedback_text = str(review_res.get("feedback", "")).lower()
            if ("dao rơi" in feedback_text or "bullish" in feedback_text or "tâm lý" in feedback_text) and sentiment_info.get("panic_score", 0) < 7:
                logger.info("🛡️ [SUPERVISOR OVERRIDE] Can thiệp phê duyệt OPEN_SHORT thuận xu hướng.")
                return {
                    "approved": True,
                    "risk_score": 3,
                    "feedback": "Duyệt OPEN_SHORT thuận xu hướng kỹ thuật 5m (Đã bỏ qua thiên kiến tin tức báo chí)."
                }

        return review_res


# -------------------------------------------------------------
# 4. REFLECTOR AGENT (Lifelong Learning & Tự tiến hóa chuẩn mực)
# -------------------------------------------------------------
class ReflectorAgent:
    SYSTEM_PROMPT = """
    You are a Senior Trading Analyst. Extract ONE concise actionable takeaway in Vietnamese (max 20 words).
    JSON format: { "analysis": "Reason for result", "lesson": "Takeaway in Vietnamese" }
    """

    SYSTEM_EVOLVE_PROMPT = """
    You are an AI Quantitative Strategy Optimizer managing a lifelong evolutionary strategy tree.
    Analyze recent trades alongside the strategy phyle.

    CRITICAL PRINCIPLES FOR SYSTEM EVOLUTION:
    1. NEVER STRIP AI EXIT RIGHTS: OperatorAgent MUST always retain the ability to propose "CLOSE" when technical momentum or 1H trends break.
    2. AVOID EXTREME STATEMENTS: Do NOT use phrases like 'HARD-LOCK', 'CẤM AI ĐÓNG LỆNH', or 'VÔ HIỆU HÓA HOÀN TOÀN AI_SIGNAL'.
    3. IMMUTABLE ENGINE STOP-LOSS: Tầng cơ học Python (PaperTrader) luôn tự động bảo vệ vốn bằng cách cắt lỗ khi nến 5m đóng cửa vi phạm EMA21 hoặc Hard-Stop -1.2%. Đây là cơ chế bảo vệ bất biến của hệ thống code lõi. BẠN TUYỆT ĐỐI KHÔNG VIẾT LUẬT ĐÒI XÓA BỎ, THAY THẾ HOẶC PHÀN NÀN VỀ CƠ CHẾ EMA21 TRONG CODE THỰC THI (như 'loại bỏ EMA21-bias', 'hard-coded EMA21'). Hãy tập trung tối ưu bộ lọc vào lệnh (Entry) và điểm chốt lời (Exit Take-Profit).
    4. BALANCED EXECUTION: Cân bằng điểm vào lệnh tối ưu để tránh bị quét dừng lỗ cơ học.
    
    JSON format:
    {
      "reason_for_update": "Lý do nâng cấp bộ luật súc tích",
      "flaw_identified": "Điểm yếu cốt lõi của phiên bản cũ vừa bộc lộ",
      "entry_rules": "Bộ quy tắc vào lệnh hoàn chỉnh mới",
      "exit_rules": "Bộ quy tắc thoát lệnh hoàn chỉnh mới"
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
        
        trade_id = self._save_to_memory(lesson, trade_summary)

        pnl_pct = trade_summary.get("pnl_pct", 0.0)
        recent_trades = self._load_recent_memory(limit=10)

        should_evolve = False
        evolve_trigger_reason = ""

        # 1. Chỉ kích hoạt tiến hóa khi LỖ THỰC SỰ do kỹ thuật (lỗ > 0.15%),
        # loại trừ các lệnh chốt lời nhẹ bị âm vài phần nghìn USDT do trừ phí sàn.
        if pnl_pct < -0.15:
            should_evolve = True
            evolve_trigger_reason = f"Phản xạ sau lệnh cắt lỗ kỹ thuật #{trade_id} ({pnl_pct:+.2f}%)"
        # 2. Định kỳ tối ưu sau mỗi 10 lệnh giao dịch thực tế trên toàn hệ thống (dựa theo trade_id)
        elif trade_id > 0 and trade_id % 10 == 0:
            should_evolve = True
            evolve_trigger_reason = f"Định kỳ tối ưu sau mốc {trade_id} lệnh giao dịch"

        if should_evolve:
            logger.info(f"⚡ [AUTO-EVOLVE] Kích hoạt tiến hóa bộ luật: {evolve_trigger_reason}")
            self.auto_evolve_rules(recent_trades)

        return lesson

    def auto_evolve_rules(self, recent_trades: list = None) -> dict:
        current_data = self.load_full_registry()
        current_ver = current_data.get("version", 1)
        history = current_data.get("evolution_history", [])

        if not recent_trades:
            recent_trades = self._load_recent_memory(limit=5)

        history_summary = [
            f"- v{h.get('version', '?')}: {h.get('reason', 'N/A')} | Vá lỗi: {h.get('flaw_identified', 'N/A')}"
            for h in history[-4:]
        ]
        history_str = "\n".join(history_summary) if history_summary else "Chưa có phả hệ cũ."

        user_prompt = f"""
LỊCH SỬ TIẾN HÓA GẦN ĐÂY:
{history_str}

BỘ QUY TẮC HIỆN TẠI (v{current_ver}):
- Lý do: {current_data.get('reason_for_update')}
- Entry Rules: {current_data.get('entry_rules')}
- Exit Rules: {current_data.get('exit_rules')}

CÁC LỆNH GẦN ĐÂY:
{json.dumps(recent_trades[-5:], ensure_ascii=False, indent=2)}

Nhiệm vụ: Viết phiên bản v{current_ver + 1}, tối ưu hóa điểm vào và điểm ra lệnh để đạt tỷ lệ thắng cao nhất. Không phàn nàn hay yêu cầu sửa đổi cơ chế cắt lỗ EMA21 cứng của engine.
"""
        evolved = _ask_llm(self.SYSTEM_EVOLVE_PROMPT, user_prompt)

        if isinstance(evolved, dict) and "exit_rules" in evolved and "entry_rules" in evolved:
            new_version = current_ver + 1
            history.append({
                "version": current_ver,
                "archived_at": datetime.now(timezone.utc).isoformat(),
                "reason": current_data.get("reason_for_update", "N/A"),
                "flaw_identified": evolved.get("flaw_identified", "Tối ưu hóa chiến lược"),
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
            logger.info(f"🎉 [TIẾN HÓA THÀNH CÔNG] Bộ luật đã tự động nâng cấp lên v{new_version}: {new_rules['reason_for_update']}")

            _send_discord_alert(
                title=f"🧬 [TIẾN HÓA BỘ QUY TẮC] v{current_ver} ➔ v{new_version}",
                description=(
                    f"**Lý do nâng cấp:** {new_rules['reason_for_update']}\n"
                    f"**Lỗ hổng đã vá:** {evolved.get('flaw_identified', 'N/A')}\n\n"
                    f"**Entry mới:** `{new_rules['entry_rules'][:700]}`\n"
                    f"**Exit mới:** `{new_rules['exit_rules'][:700]}`"
                ),
                color=0x9B59B6
            )
            return new_rules

        logger.warning("⚠️ LLM không sinh đủ cấu trúc rules mới, tiếp tục duy trì phiên bản hiện tại.")
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

    def _save_to_memory(self, lesson: str, trade_summary: dict) -> int:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        history = []
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []

        new_id = len(history) + 1
        history.append({
            "id": new_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "side": trade_summary.get("side", "NONE"),
            "pnl_pct": trade_summary.get("pnl_pct", 0.0),
            "exit_reason": trade_summary.get("exit_reason", "MANUAL"),
            "lesson": lesson
        })

        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        return new_id

    def _load_recent_memory(self, limit: int = 10) -> list:
        if not MEMORY_FILE.exists():
            return []
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data[-limit:]
        except Exception:
            return []

    @staticmethod
    def load_lessons(side: str = None) -> list:
        if not MEMORY_FILE.exists():
            return []
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not data:
                return []

            loss_trades = [d for d in data if d.get("pnl_pct", 0) < -0.15][-3:]
            critical_lessons = [f"[CẢNH BÁO LỖ #{d.get('id')} ({d.get('pnl_pct'):.2f}%)] {d.get('lesson')}" for d in loss_trades]

            recent_trades = [d for d in data if side is None or d.get("side") == side][-2:]
            recent_lessons = [f"[GẦN ĐÂY #{d.get('id')}] {d.get('lesson')}" for d in recent_trades]

            combined = list(dict.fromkeys(critical_lessons + recent_lessons))
            return combined if combined else ["Tuân thủ nghiêm kỷ luật cắt lỗ và chỉ báo."]
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
        user_prompt = f"Lỗi hệ thống:\n{traceback_str}\nPhân tích và trả về JSON."
        return _ask_llm(self.SYSTEM_PROMPT, user_prompt)


# -------------------------------------------------------------
# 6. AGENT TEAM (Đóng gói hoàn chỉnh)
# -------------------------------------------------------------
class AgentTeam:
    def __init__(self, config=None):
        self.config = config
        self.strategist = StrategistAgent(config)
        self.operator = OperatorAgent(config)
        self.supervisor = SupervisorAgent(config)
        self.reflector = ReflectorAgent(config)
        self.auditor = AuditorAgent(config)

        from agents.sentiment_agent import SentimentAgent
        self.sentiment = SentimentAgent(config)

        self.strategist_agent = self.strategist
        self.operator_agent = self.operator
        self.supervisor_agent = self.supervisor
        self.reflector_agent = self.reflector
        self.auditor_agent = self.auditor
        self.sentiment_agent = self.sentiment
import os
import time
import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Nạp cấu hình từ .env
load_dotenv(encoding="utf-8")

def run_test(name: str, base_url: str, api_key: str, model: str):
    print(f"\n{'='*55}")
    print(f"🧪 Đang kiểm tra: {name}")
    print(f"   Endpoint : {base_url}")
    print(f"   Model    : {model}")
    print(f"{'='*55}")

    if not api_key and "groq" in base_url.lower():
        print("❌ THẤT BẠI: Chưa cấu hình API Key trong file .env!")
        return False

    client = OpenAI(
        base_url=base_url,
        api_key=api_key or "ollama",
        timeout=25.0
    )

    system_prompt = "You are a quantitative trading agent. Return strictly valid JSON."
    user_prompt = (
        'Evaluate market condition: BTC=84200, RSI=66. '
        'Return JSON format: {"action": "HOLD", "confidence": 0.7, "model_verified": "' + model + '"}'
    )

    start_time = time.time()
    try:
        res = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=150
        )
        latency = time.time() - start_time
        raw_output = res.choices[0].message.content.strip()

        # Làm sạch và thẩm định JSON
        clean_text = raw_output.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)

        print(f"✅ THÀNH CÔNG ({latency:.2f}s)")
        print(f"   Phản hồi JSON: {data}")
        return True

    except Exception as err:
        latency = time.time() - start_time
        print(f"❌ THẤT BẠI ({latency:.2f}s)")
        print(f"   Chi tiết lỗi: {err}")
        return False


# 1. Test Ollama Cloud (Tier 2)
ollama_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
ollama_model = os.getenv("LOCAL_LLM_MODEL", "gemma4:31b-cloud")
ollama_key = os.getenv("LOCAL_LLM_API_KEY", "ollama")
test_ollama = run_test("OLLAMA CLOUD (Tier 2)", ollama_url, ollama_key, ollama_model)

# 2. Test Groq Cloud (Tier 3)
groq_url = "https://api.groq.com/openai/v1"
groq_model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
groq_key = os.getenv("GROQ_API_KEY")
test_groq = run_test("GROQ CLOUD (Tier 3)", groq_url, groq_key, groq_model)

print(f"\n{'-'*55}")
print(f"KẾT QUẢ TỔNG HỢP: Ollama: {'PASS' if test_ollama else 'FAIL'} | Groq: {'PASS' if test_groq else 'FAIL'}")
print(f"{'-'*55}")
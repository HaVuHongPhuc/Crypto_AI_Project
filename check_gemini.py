import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
)

# Danh sách các model bạn có hạn ngạch lớn trong bảng
candidates = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3-flash",
]

print("🔍 ĐANG KIỂM TRA ĐỘ ỔN ĐỊNH CÁC MODEL CỦA GOOGLE...")
for m in candidates:
  try:
    res = client.chat.completions.create(
        model=m,
        messages=[{"role": "user", "content": "Ping test 1+1=?"}],
        timeout=5.0,
    )
    print(f"✅ MODEL [{m}]: HOẠT ĐỘNG TỐT (HTTP 200)")
  except Exception as e:
    print(f"❌ MODEL [{m}]: NGHẼN/LỖI ({str(e)[:60]}...)")
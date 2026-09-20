import json
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
)

model_name = os.getenv("LLM_MODEL_NAME")
print(f"Đang kiểm tra kết nối tới model: {model_name}...")

response = client.chat.completions.create(
    model=model_name,
    response_format={"type": "json_object"},
    messages=[
        {
            "role": "system",
            "content": "You are a JSON-only response engine. Output ONLY a valid raw JSON object. Never include explanations, greetings, preamble, or markdown code fences.",
        },
        {
            "role": "user",
            "content": 'Return a JSON object with keys "status" and "agent", with values "ok" and "ready".',
        },
    ],
    temperature=0.1,
)

data = json.loads(response.choices[0].message.content)
print("\n Kết nối thành công! Phản hồi từ mô hình:")
print(json.dumps(data, indent=2, ensure_ascii=False))
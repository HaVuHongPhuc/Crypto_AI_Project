from datetime import datetime, timezone
import json
from pathlib import Path

RULES_FILE = Path("storage/strategy_rules.json")

# Dữ liệu hiện tại v8 của bạn
current_v8 = {
    "version": 8,
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "reason_for_update": (
        "Tăng độ lỳ cho lệnh, loại bỏ chốt lời non, chỉ thoát khi EMA21 bị phá"
        " vỡ dứt khoát và RSI xác nhận đảo chiều."
    ),
    "entry_rules": (
        "OPEN_LONG khi EMA9 > EMA21 và RSI > 50. OPEN_SHORT khi EMA9 < EMA21 và"
        " RSI < 50. Yêu cầu xu hướng khung 1H đồng thuận."
    ),
    "exit_rules": (
        "Cấm thoát lệnh dựa trên biến động giá ngắn hạn. Chỉ đóng vị thế khi"
        " nến đóng cửa hoàn toàn phía bên kia EMA21. Bắt buộc RSI phải xác nhận"
        " đảo chiều (<50 với Long, >50 với Short)."
    ),
    # Tái hiện phả hệ tiến hóa từ v1 đến v7
    "evolution_history": [
        {
            "version": 1,
            "reason": "Quy tắc khởi tạo chuẩn kỹ thuật EMA9/21 và RSI 50.",
            "flaw_identified": (
                "Chưa có chỉ thị khung 1H, dễ bị nhiễu sóng ngắn."
            ),
        },
        {
            "version": 2,
            "reason": (
                "Thêm yêu cầu đồng thuận 1H (ONLY_LONG / ONLY_SHORT) từ"
                " Strategist."
            ),
            "flaw_identified": "Thoát lệnh quá vội khi giá chạm nhẹ EMA9.",
        },
        {
            "version": 3,
            "reason": (
                "Cải tiến quy tắc: Cho phép giá retest EMA9 mà không đóng lệnh."
            ),
            "flaw_identified": (
                "Vẫn chốt lời non ở mức +0.05% do sợ mất lợi nhuận."
            ),
        },
        {
            "version": 4,
            "reason": "Thiết lập mục tiêu lợi nhuận tối thiểu trước khi đóng.",
            "flaw_identified": (
                "Cắt lỗ sai khi thị trường rút chân tạo nến Pinbar."
            ),
        },
        {
            "version": 5,
            "reason": "Yêu cầu nến đóng cửa hoàn toàn dưới EMA mới xét cắt.",
            "flaw_identified": "Chưa kết hợp xung lực RSI khi thoát lệnh.",
        },
        {
            "version": 6,
            "reason": "Bổ sung điều kiện RSI gãy 50 khi đóng vị thế.",
            "flaw_identified": (
                "Chưa phân định rõ ranh giới giữa EMA9 và EMA21."
            ),
        },
        {
            "version": 7,
            "reason": (
                "Chuyển mốc hỗ trợ/kháng cự động chính từ EMA9 sang EMA21."
            ),
            "flaw_identified": (
                "Cần gia tăng thêm độ lỳ trong sóng biến động mạnh."
            ),
        },
    ],
}

with open(RULES_FILE, "w", encoding="utf-8") as f:
  json.dump(current_v8, f, ensure_ascii=False, indent=2)

print(
    "✅ ĐÃ NÂNG CẤP THÀNH CÔNG SỔ CÁI PHẢ HỆ TIẾN HÓA! v8 hiện đã mang đầy đủ ký"
    " ức từ v1 đến v7."
)
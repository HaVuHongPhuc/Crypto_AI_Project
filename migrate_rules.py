from datetime import datetime, timezone
import json
from pathlib import Path

RULES_FILE = Path("storage/strategy_rules.json")
RULES_FILE.parent.mkdir(parents=True, exist_ok=True)

rules_v11 = {
    "version": 11,
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "reason_for_update": (
        "Vô hiệu hóa hoàn toàn can thiệp AI, ép buộc hệ thống tuân thủ kỷ luật"
        " kỹ thuật cứng để tối ưu hóa lợi nhuận."
    ),
    "entry_rules": (
        "OPEN_LONG khi EMA9 > EMA21, RSI > 50 và khung 1H là ONLY_LONG."
        " OPEN_SHORT khi EMA9 < EMA21, RSI < 50 và khung 1H là ONLY_SHORT."
    ),
    "exit_rules": (
        "CẤM TUYỆT ĐỐI mọi can thiệp từ AI_EARLY_EXIT_CLOSE. Chỉ đóng lệnh khi"
        " nến đóng cửa hoàn toàn phía bên kia EMA21 VÀ RSI xác nhận đảo chiều"
        " (<50 với Long, >50 với Short)."
    ),
    # Phả hệ tiến hóa trọn vẹn từ v1 đến v10
    "evolution_history": [
        {
            "version": 1,
            "reason": "Quy tắc khởi tạo chuẩn kỹ thuật EMA9/21 và RSI 50.",
            "flaw_identified": "Chưa có chỉ thị khung 1H, dễ bị nhiễu sóng ngắn."
        },
        {
            "version": 2,
            "reason": "Thêm yêu cầu đồng thuận 1H (ONLY_LONG / ONLY_SHORT) từ Strategist.",
            "flaw_identified": "Thoát lệnh quá vội khi giá chạm nhẹ EMA9."
        },
        {
            "version": 3,
            "reason": "Cải tiến quy tắc: Cho phép giá retest EMA9 mà không đóng lệnh.",
            "flaw_identified": "Vẫn chốt lời non ở mức +0.05% do sợ mất lợi nhuận."
        },
        {
            "version": 4,
            "reason": "Thiết lập mục tiêu lợi nhuận tối thiểu trước khi đóng.",
            "flaw_identified": "Cắt lỗ sai khi thị trường rút chân tạo nến Pinbar."
        },
        {
            "version": 5,
            "reason": "Yêu cầu nến đóng cửa hoàn toàn dưới EMA mới xét cắt.",
            "flaw_identified": "Chưa kết hợp xung lực RSI khi thoát lệnh."
        },
        {
            "version": 6,
            "reason": "Bổ sung điều kiện RSI gãy 50 khi đóng vị thế.",
            "flaw_identified": "Chưa phân định rõ ranh giới giữa EMA9 và EMA21."
        },
        {
            "version": 7,
            "reason": "Chuyển mốc hỗ trợ/kháng cự động chính từ EMA9 sang EMA21.",
            "flaw_identified": "Cần gia tăng thêm độ lỳ trong sóng biến động mạnh."
        },
        {
            "version": 8,
            "reason": "Tăng độ lỳ cho lệnh, loại bỏ chốt lời non, chỉ thoát khi EMA21 bị phá vỡ dứt khoát.",
            "flaw_identified": "AI vẫn cố tìm lý do đóng lệnh sớm khi thấy nến đỏ ngắn hạn."
        },
        {
            "version": 9,
            "reason": "Giới hạn quyền đóng lệnh của LLM, bổ sung kiểm tra Trailing Stop cơ học.",
            "flaw_identified": "Độ trễ suy luận của LLM làm trễ nhịp thoát lệnh khẩn cấp."
        },
        {
            "version": 10,
            "reason": "Tách biệt hoàn toàn tầng RiskManager cơ học 0ms khỏi quyết định của Agent.",
            "flaw_identified": "Cần điều khoản cấm dứt điểm hành vi AI_EARLY_EXIT_CLOSE trong prompt."
        }
    ]
}

with open(RULES_FILE, "w", encoding="utf-8") as f:
    json.dump(rules_v11, f, ensure_ascii=False, indent=2)

print("✅ ĐÃ ĐỒNG BỘ THÀNH CÔNG V11! Hệ thống giữ nguyên v11 và mang trọn vẹn ký ức từ v1 đến v10.")
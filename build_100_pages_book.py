"""
BUILD_100_PAGES_BOOK.PY
Đường ống tự động điều phối AI Local (Ollama - gemma4:12b) viết Báo cáo Khoa học & Đặc tả Kỹ thuật
dài 100 trang A4 (~45.000 - 50.000 từ) và xuất thẳng ra file Word (.docx).
"""

import os
import json
import time
import urllib.request
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Cấu hình API Ollama Local với model gemma4:12b
OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
MODEL_NAME = "gemma4:12b"

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = "Dac_Ta_Toan_Dien_He_Thong_Crypto_AI_100_Trang.docx"

# DANH SÁCH 25 TIỂU MỤC CHUYÊN SÂU ĐẢM BẢO DUNG LƯỢNG 100 TRANG
SECTIONS = [
    # CHƯƠNG 1
    {"id": "1.1", "chap": "CHƯƠNG 1: TỔNG QUAN KIẾN TRÚC & TOPOLOGY HỆ THỐNG", 
     "title": "Bối cảnh thị trường tiền mã hóa tần suất cao & Triết lý thiết kế Hybrid (ML + Multi-Agent)",
     "prompt": "Phân tích bối cảnh thị trường BTC/USDT biến động nhanh, nhược điểm của bot truyền thống (grid/dca), triết lý kết hợp Random Forest với 6 LLM Agents."},
    {"id": "1.2", "chap": "CHƯƠNG 1: TỔNG QUAN KIẾN TRÚC & TOPOLOGY HỆ THỐNG",
     "title": "Sơ đồ luồng dữ liệu (Dataflow) & Quyền điều khiển (Control Flow) xuyên suốt 6 tầng",
     "prompt": "Vẽ sơ đồ ASCII/Text chi tiết và mô tả luồng tín hiệu từ Binance API -> Preprocessor -> Model -> Strategist 1H -> Operator 5m -> Supervisor -> PaperTrader -> Reflector."},
    {"id": "1.3", "chap": "CHƯƠNG 1: TỔNG QUAN KIẾN TRÚC & TOPOLOGY HỆ THỐNG",
     "title": "Bản đồ cấu trúc thư mục, giao ước Module và cấu hình môi trường .env",
     "prompt": "Đặc tả chi tiết từng file trong cây thư mục dự án, vai trò của từng biến môi trường trong .env và nguyên tắc bảo mật API Key."},

    # CHƯƠNG 2
    {"id": "2.1", "chap": "CHƯƠNG 2: DATA PIPELINE & 7 CHIỀU ĐẶC TRƯNG ĐỊNH LƯỢNG",
     "title": "Pipeline thu thập dữ liệu đa khung thời gian từ Binance REST API",
     "prompt": "Đặc tả quá trình tải batch 35,000 nến 5m và nến 1H từ Binance API, lưu trữ CSV tại storage/btc_5m.csv, quản lý Rate Limit."},
    {"id": "2.2", "chap": "CHƯƠNG 2: DATA PIPELINE & 7 CHIỀU ĐẶC TRƯNG ĐỊNH LƯỢNG",
     "title": "Cơ sở toán học & Công thức tính toán chi tiết của 7 đặc trưng kỹ thuật",
     "prompt": "Trình bày công thức toán học giải tích chi tiết của 7 chỉ báo: RSI(14), MACD(12,26,9), MACD Signal, EMA(9), EMA(21), EMA Spread Pct, Volume Change."},
    {"id": "2.3", "chap": "CHƯƠNG 2: DATA PIPELINE & 7 CHIỀU ĐẶC TRƯNG ĐỊNH LƯỢNG",
     "title": "Cơ chế làm sạch dữ liệu, khử nhiễu và triệt tiêu Lookahead Bias",
     "prompt": "Giải thích Lookahead Bias trong chuỗi thời gian, cách xử lý NaN, rolling window và việc không dùng shuffle khi chia dữ liệu."},

    # CHƯƠNG 3
    {"id": "3.1", "chap": "CHƯƠNG 3: MÔ HÌNH HỌC MÁY RANDOM FOREST & SỬA LỖI ĐẢO NHÃN",
     "title": "Logic gán nhãn mục tiêu tương lai (Fixed Forward Window 4 nến)",
     "prompt": "Phân tích logic quét 4 nến tương lai (20 phút), điều kiện tăng trưởng >= 0.35% gán BUY ngược lại HOLD trong hàm create_labels của train.py."},
    {"id": "3.2", "chap": "CHƯƠNG 3: MÔ HÌNH HỌC MÁY RANDOM FOREST & SỬA LỖI ĐẢO NHÃN",
     "title": "Cấu trúc rừng cây quyết định Random Forest & Cân bằng mẫu class_weight",
     "prompt": "Đặc tả thuật toán Random Forest, n_estimators=250, max_depth=8, min_samples_leaf=15, giải quyết mất cân bằng mẫu (85% HOLD vs 15% BUY)."},
    {"id": "3.3", "chap": "CHƯƠNG 3: MÔ HÌNH HỌC MÁY RANDOM FOREST & SỬA LỖI ĐẢO NHÃN",
     "title": "Giải phẫu lỗi đảo ngược nhãn Alphabet (classes_) và Ma trận nhầm lẫn",
     "prompt": "Phân tích sâu lỗi ngớ ngẩn: scikit-learn sắp xếp nhãn alphabet khiến index [0][1] bị đảo thành HOLD. Cách sửa triệt để bằng classes.index('BUY'). Phân tích Confusion Matrix."},

    # CHƯƠNG 4
    {"id": "4.1", "chap": "CHƯƠNG 4: WALK-FORWARD RETRAINING NGẦM & HOT-SWAP RAM",
     "title": "Luồng chạy ngầm đa tiểu trình (Threading) đếm chu kỳ 2,016 nến (7 ngày)",
     "prompt": "Đặc tả luồng threading.Thread chạy ngầm trong main.py, cơ chế đếm nến và kích hoạt ml_retrainer.py sau mỗi 7 ngày mà không chặn nến 5m."},
    {"id": "4.2", "chap": "CHƯƠNG 4: WALK-FORWARD RETRAINING NGẦM & HOT-SWAP RAM",
     "title": "Kiểm định mẫu ngoài (Out-of-Sample OOS Validation) & Tiêu chuẩn nghiệm thu",
     "prompt": "Quy trình kiểm tra độ chính xác trên tập dữ liệu kiểm thử OOS, điều kiện chấp nhận model mới trước khi ghi đè model.pkl."},
    {"id": "4.3", "chap": "CHƯƠNG 4: WALK-FORWARD RETRAINING NGẦM & HOT-SWAP RAM",
     "title": "Cơ chế Hot-Swap nạp model.pkl trực tiếp vào RAM và xử lý xung đột Joblib/Pickle",
     "prompt": "Mã nguồn và nguyên lý hàm reload_model(), load_ml_model() hỗ trợ cả joblib và pickle chống lỗi STACK_GLOBAL requires str."},

    # CHƯƠNG 5
    {"id": "5.1", "chap": "CHƯƠNG 5: HẠ TẦNG 3-TIER WATERFALL LLM CHỊU LỖI CAO",
     "title": "Kiến trúc điều phối thác nước 3 tầng: Gemini -> Gemma 4 -> Groq Cloud",
     "prompt": "Phân tích vai trò của từng tầng: Tier 1 (Gemini 3.1 Flash Lite), Tier 2 (Ollama Gemma 4 Cloud), Tier 3 (Groq Qwen 27B siêu tốc 0.3s)."},
    {"id": "5.2", "chap": "CHƯƠNG 5: HẠ TẦNG 3-TIER WATERFALL LLM CHỊU LỖI CAO",
     "title": "Thuật toán xử lý ngoại lệ HTTP 503, Exponential Backoff và Offline Shield",
     "prompt": "Cơ chế bắt mã lỗi 503 Service Unavailable, tự động retry và fallback sang Tier 2/3. Cơ chế kích hoạt HOLD an toàn khi mất mạng toàn bộ."},
    {"id": "5.3", "chap": "CHƯƠNG 5: HẠ TẦNG 3-TIER WATERFALL LLM CHỊU LỖI CAO",
     "title": "Bộ phân tích cú pháp trích xuất JSON an toàn chống Markdown Fences (_extract_json)",
     "prompt": "Phân tích mã nguồn hàm _extract_json, dùng regex bóc tách JSON khi LLM trả về markdown ```json ``` hoặc text thừa."},

    # CHƯƠNG 6
    {"id": "6.1", "chap": "CHƯƠNG 6: TÁC TỬ VĨ MÔ STRATEGIST & PHẢN XẠ 1H",
     "title": "Phá vỡ bẫy trễ EMA200: Tại sao giao cắt EMA50/EMA200 làm tê liệt phe Short?",
     "prompt": "Phân tích lỗi thiết kế kinh điển: chờ EMA50 cắt EMA200 trên 1H mất tới hàng tuần khiến bot bỏ lỡ sóng giảm. Cách loại bỏ bẫy này."},
    {"id": "6.2", "chap": "CHƯƠNG 6: TÁC TỬ VĨ MÔ STRATEGIST & PHẢN XẠ 1H",
     "title": "Thuật toán phản xạ tức thì với EMA50 và RSI 1H ban hành 3 chỉ thị vĩ mô",
     "prompt": "Đặc tả điều kiện ban hành ONLY_LONG (Giá > EMA50, RSI > 52), ONLY_SHORT (Giá < EMA50, RSI < 48) và FLEXIBLE của StrategistAgent."},

    # CHƯƠNG 7
    {"id": "7.1", "chap": "CHƯƠNG 7: TÁC TỬ THỰC THI OPERATOR TRÊN NẾN 5M",
     "title": "Ma trận đồng thuận 3 nhân tố: Kỹ thuật 5m + Xác suất ML + Bộ luật hiện hành vN",
     "prompt": "Đặc tả hàm OperatorAgent.analyze(), cách nạp indicators 5m, đọc luật từ strategy_rules.json và kết hợp ML Buy Probability."},
    {"id": "7.2", "chap": "CHƯƠNG 7: TÁC TỬ THỰC THI OPERATOR TRÊN NẾN 5M",
     "title": "Không gian trạng thái hành động & Ngưỡng kích hoạt lệnh (OPEN_LONG / SHORT / CLOSE / HOLD)",
     "prompt": "Quy tắc mở Long (ML > 65%, EMA9 > EMA21, RSI > 55), mở Short (ML < 35%, EMA9 < EMA21, RSI < 45) và điều kiện đóng vị thế."},

    # CHƯƠNG 8
    {"id": "8.1", "chap": "CHƯƠNG 8: TÁC TỬ GIÁM SÁT SUPERVISOR & TIN TỨC THỊ TRƯỜNG",
     "title": "Quyền phủ quyết (Veto Power) của Supervisor & Tình báo tin tức SentimentAgent",
     "prompt": "Đặc tả SentimentAgent cào RSS, tính toán Panic Score (1-10), Black Swan Alert và thẩm định của SupervisorAgent."},
    {"id": "8.2", "chap": "CHƯƠNG 8: TÁC TỬ GIÁM SÁT SUPERVISOR & TIN TỨC THỊ TRƯỜNG",
     "title": "Phân định Trend Following Short vs Bắt dao rơi & Python Override Guard",
     "prompt": "Quy tắc thép: Mở Short khi gãy EMA là thuận xu hướng, cấm từ chối vì 'bắt dao rơi'. Phân tích đoạn code can thiệp Override Guard ở cấp Python."},

    # CHƯƠNG 9
    {"id": "9.1", "chap": "CHƯƠNG 9: ĐỘNG CƠ PAPERTRADER & BỘ GIÁP RỦI RO CƠ HỌC",
     "title": "Động lực học phân bổ vốn (70u Trend vs 30u Flexible) & Mô hình hóa phí sàn 0.05%",
     "prompt": "Đặc tả quản trị quy mô vị thế theo chỉ thị 1H, trừ phí khớp lệnh 0.05% hai đầu mua/bán, tính toán số dư tiền mặt thực tế."},
    {"id": "9.2", "chap": "CHƯƠNG 9: ĐỘNG CƠ PAPERTRADER & BỘ GIÁP RỦI RO CƠ HỌC",
     "title": "Bộ ba chốt chặn: Hard Stop-Loss (-1.2%), Take Profit (+1.5%) & Trailing Stop động",
     "prompt": "Thuật toán cắt lỗ cứng cưỡng chế của PaperTrader không phụ thuộc AI; cơ chế Trailing Stop kích hoạt tại +0.4% và trượt 0.5% khóa lãi."},
    {"id": "9.3", "chap": "CHƯƠNG 9: ĐỘNG CƠ PAPERTRADER & BỘ GIÁP RỦI RO CƠ HỌC",
     "title": "Lưu vết và phục hồi trạng thái vị thế (State Persistence) active_position.json",
     "prompt": "Cơ chế đọc và ghi đè active_position.json, nạp lại vị thế cũ khi tắt/bật lại bot mà không mất giá vào lệnh và số nến holding."},

    # CHƯƠNG 10
    {"id": "10.1", "chap": "CHƯƠNG 10: TÁC TỬ PHẢN TƯ REFLECTOR & TỰ TIẾN HÓA BỘ LUẬT TRỌN ĐỜI",
     "title": "Cơ chế phản tư sau lệnh đóng và ghi sổ cái vĩnh viễn memory.json",
     "prompt": "Đặc tả hàm reflect(), trích xuất bài học tiếng Việt dưới 20 từ, lưu vào memory.json và truyền tải cho các lần ra quyết định sau."},
    {"id": "10.2", "chap": "CHƯƠNG 10: TÁC TỬ PHẢN TƯ REFLECTOR & TỰ TIẾN HÓA BỘ LUẬT TRỌN ĐỜI",
     "title": "Thuật toán đột biến quy tắc (v1 -> v15+) và giải quyết lỗi tràn token 400 Bad Request",
     "prompt": "Phân tích điều kiện tự động kích hoạt tiến hóa (PnL < 0 hoặc đủ 5 lệnh). Phân tích lỗi json_validate_failed khi max_tokens=500 và cách giải quyết bằng max_tokens=2000."},
    {"id": "10.3", "chap": "CHƯƠNG 10: TÁC TỬ PHẢN TƯ REFLECTOR & TỰ TIẾN HÓA BỘ LUẬT TRỌN ĐỜI",
     "title": "Tác tử Auditor SRE, Hệ thống Telemetry Discord & Lộ trình mở rộng Live Trading",
     "prompt": "Đặc tả AuditorAgent bắt traceback lỗi, thông báo Rich Embed Discord Webhook, và các bước chuẩn bị kết nối API Binance thực tế."}
]

def generate_section_content(sec, retry_count=3):
    """Gửi yêu cầu đến Ollama local (gemma4:12b) để viết sâu từng tiểu mục."""
    system_prompt = (
        "Bạn là Viện trưởng Viện Nghiên cứu Định lượng kiêm Principal Systems Architect. "
        "Nhiệm vụ của bạn là viết một phần của BÁO CÁO KHOA HỌC & ĐẶC TẢ HỆ THỐNG GIAO DỊCH ĐỊNH LƯỢNG CRYPTO AI (BTC/USDT 5M). "
        "Yêu cầu: Viết bằng TIẾNG VIỆT học thuật, cực kỳ chi tiết, phân tích sâu từng ngóc ngách, công thức toán học, thuật toán, "
        "mã giả pseudocode, cấu trúc dữ liệu JSON và cơ chế bảo vệ rủi ro. Tuyệt đối KHÔNG viết tóm tắt sơ sài, "
        "hãy viết sâu và dài đầy đặn tương đương 3-4 trang A4 cho tiểu mục này."
    )
    
    user_prompt = f"""
TIỂU MỤC CẦN VIẾT: [{sec['id']}] {sec['title']}
THUỘC: {sec['chap']}

NỘI DUNG TRỌNG TÂM CẦN MỔ XẺ CHI TIẾT:
{sec['prompt']}

HÃY VIẾT BÀI ĐẶC TẢ HOÀN CHỈNH CHO TIỂU MỤC NÀY THEO CẤU TRÚC:
1. Đặt vấn đề và mục tiêu kỹ thuật.
2. Cơ sở lý thuyết và công thức toán học định lượng.
3. Thuật toán chi tiết & Mã giả (Pseudocode) hoặc phân tích code thực tế.
4. Giao thức dữ liệu (Data Schema / JSON / DataFrame).
5. Phân tích các trường hợp biên (Edge Cases), bẫy lỗi tiềm ẩn và cách phòng vệ.
"""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
        "options": {
            "num_ctx": 4096,
            "temperature": 0.2
        }
    }
    
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    for attempt in range(retry_count):
        try:
            with urllib.request.urlopen(req, timeout=360) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"⚠️ Lỗi kết nối Ollama ở mục {sec['id']} (Lần {attempt + 1}): {e}")
            time.sleep(5)
            
    return f"Lỗi không thể sinh nội dung cho mục {sec['id']} sau 3 lần thử."

def append_to_word_doc(doc, sec, content):
    """Ghi nội dung của tiểu mục vào tài liệu Word."""
    h1 = doc.add_heading(f"MỤC {sec['id']}: {sec['title'].upper()}", level=1)
    h1.paragraph_format.space_before = Pt(16)
    h1.paragraph_format.space_after = Pt(8)
    
    chap_p = doc.add_paragraph()
    chap_run = chap_p.add_run(f"Thuộc: {sec['chap']}")
    chap_run.italic = True
    chap_run.font.color.rgb = RGBColor(0x7F, 0x8C, 0x8D)
    chap_p.paragraph_format.space_after = Pt(12)

    lines = content.split("\n")
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        if line_str.startswith("### "):
            h3 = doc.add_heading(line_str[4:], level=3)
            h3.paragraph_format.space_before = Pt(10)
        elif line_str.startswith("## "):
            h2 = doc.add_heading(line_str[3:], level=2)
            h2.paragraph_format.space_before = Pt(12)
        elif line_str.startswith("- ") or line_str.startswith("* "):
            p = doc.add_paragraph(line_str[2:], style='List Bullet')
            p.paragraph_format.line_spacing = 1.15
        elif line_str.startswith("1. ") or line_str.startswith("2. ") or line_str.startswith("3. ") or line_str.startswith("4. ") or line_str.startswith("5. "):
            p = doc.add_paragraph(line_str[3:], style='List Number')
            p.paragraph_format.line_spacing = 1.15
        else:
            p = doc.add_paragraph(line_str)
            p.paragraph_format.line_spacing = 1.2
            p.paragraph_format.space_after = Pt(4)

    doc.add_page_break()

def main():
    print("=" * 70)
    print("📚 BẮT ĐẦU ĐƯỜNG ỐNG TỰ ĐỘNG BIÊN SOẠN BÁO CÁO KHOA HỌC 100 TRANG")
    print(f"Tổng số tiểu mục cần xuất bản: {len(SECTIONS)} mục (~4 trang/mục)")
    print(f"Mô hình AI Local sử dụng: {MODEL_NAME}")
    print("=" * 70)
    
    doc = Document()
    
    # Cấu hình lề trang chuẩn A4
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(0.8)

    # Trang bìa chính
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t_run = title_p.add_run("\n\n\nBÁO CÁO KHOA HỌC & ĐẶC TẢ KIẾN TRÚC TOÀN DIỆN\n")
    t_run.font.size = Pt(16)
    t_run.font.bold = True
    
    m_run = title_p.add_run("HỆ THỐNG GIAO DỊCH ĐỊNH LƯỢNG ĐA TÁC TỬ TỰ THÍCH NGHI VÀ TIẾN HÓA TRỌN ĐỜI\n(CRYPTO AI QUANT TRADING SYSTEM - BTC/USDT 5M)\n\n")
    m_run.font.size = Pt(22)
    m_run.font.bold = True
    m_run.font.color.rgb = RGBColor(0x2C, 0x3E, 0x50)

    sub_p = doc.add_paragraph()
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub_run = sub_p.add_run("Tài liệu nghiên cứu & Đặc tả kỹ thuật cấp độ Production\nDung lượng: ~100 Trang A4 | Định dạng: Technical Whitepaper")
    sub_run.font.size = Pt(12)
    sub_run.italic = True
    
    doc.add_page_break()

    total = len(SECTIONS)
    for idx, sec in enumerate(SECTIONS, start=1):
        print(f"\n⏳ [{idx:02d}/{total:02d}] Đang biên soạn chuyên sâu: Mục {sec['id']} - {sec['title']}...")
        start_time = time.time()
        
        content = generate_section_content(sec)
        append_to_word_doc(doc, sec, content)
        
        doc.save(OUTPUT_FILE)
        
        elapsed = time.time() - start_time
        print(f"✅ Hoàn thành mục {sec['id']} ({elapsed:.1f}s) -> Đã lưu vào {OUTPUT_FILE}")

    print("\n" + "=" * 70)
    print(f"🎉 CHÚC MỪNG! TOÀN BỘ 25 TIỂU MỤC ĐÃ ĐƯỢC XUẤT THÀNH CÔNG BẰNG {MODEL_NAME}!")
    print(f"📁 Tệp tài liệu Word lưu tại: {os.path.abspath(OUTPUT_FILE)}")
    print("=" * 70)

if __name__ == "__main__":
    main()
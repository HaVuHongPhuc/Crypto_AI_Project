# Hướng dẫn cho Codex và người phát triển

## Mục đích

Repo là bot paper trading BTC/USDT dùng dữ liệu Binance, LLM nhiều tác tử và trạng thái cục bộ. Tài liệu này phản ánh mã hiện tại; khi README, comment hoặc script cũ khác với mã thực thi, hãy kiểm tra đường chạy thực tế.

## Bản đồ

- main.py: vòng lặp bot chính.
- agents/agent_team.py: Strategist, Operator, Supervisor, Reflector, Auditor và gọi LLM.
- agents/sentiment_agent.py: Fear & Greed, RSS và phân tích tâm lý.
- config/env.py: nạp .env từ thư mục gốc bằng đường dẫn tuyệt đối; config/settings.py dùng chung loader và kiểm tra Settings.
- data/fetcher.py, data/preprocessor.py: OHLCV, chỉ báo và nhãn.
- train.py, models/predictor.py, models/model.pkl: pipeline Random Forest độc lập.
- engine/paper_trader.py: ledger paper, phí hai chiều, lịch sử và phục hồi cash/vị thế.
- engine/risk_manager.py: SL/TP/trailing LONG/SHORT; main gọi kiểm tra giá mỗi vòng.
- notifiers/discord.py: Discord webhook.
- storage/: dữ liệu thị trường, luật, memory, vị thế, log và lịch sử giao dịch.
- fetch_and_save_dataset.py: tải lịch sử và ghi CSV.
- migrate_rules.py: ghi đè luật hiện hành bằng v8.
- summary.py, export_report.py, build_100_pages_book.py: tiện ích báo cáo.
- check_gemini.py, test_llm.py: kiểm tra LLM riêng.
- test_system_flow.py: script tích hợp có gọi mạng và sửa file trạng thái; không phải test chỉ đọc.

## Luồng đang chạy trong main.py

1. Settings nạp .env và kiểm tra tham số. PaperTrader khôi phục cash/vị thế; AgentTeam và DiscordNotifier được tạo. main giữ process lock để tránh hai bot sửa chung ledger.
2. Mỗi vòng lấy ticker hiện tại để quản lý rủi ro, rồi tải OHLCV theo CANDLE_LIMIT. Bỏ kline cuối đang hình thành và tính các feature bằng add_indicators, khớp thứ tự feature model.
3. Chỉ phân tích khi timestamp của nến đã đóng thay đổi. Giá ticker dùng để mô phỏng entry/exit; chỉ báo dùng nến đã đóng.
4. SentimentAgent lấy Fear & Greed từ alternative.me và tối đa 6 tiêu đề Cointelegraph RSS, rồi nhờ LLM phân tích. Kết quả cache 900 giây.
5. OperatorAgent nhận giá/chỉ báo/vị thế/luật và yêu cầu LLM trả OPEN_LONG, OPEN_SHORT, CLOSE hoặc HOLD.
6. Supervisor xác thực action/schema/cash/confidence/macro/technical/sentiment rồi mới nhờ LLM duyệt lệnh mở. main kiểm tra lại hard invariants trước khi thay đổi portfolio.
7. Stake là POSITION_SIZE_PCT của cash. RiskManager chạy mỗi vòng; EMA21/RSI đóng theo nến mới. Khi đóng, ledger và trades.csv được cập nhật sau phí; Reflector lưu bài học và có thể gửi Discord.
8. Vòng lặp ngủ theo LOOP_SECONDS; exception được log, đưa cho Auditor phân tích, rồi retry sau ít nhất 10 giây. Ctrl+C dừng bot và thả process lock.
9. Chỉ giữ một vị thế. Đây là paper trading; main không gửi lệnh thật lên sàn.

## Quan hệ giữa các module

- main gọi Strategist với EMA50/EMA200 và RSI trên nến 1H đã đóng; thiếu dữ liệu thì directive NO_TRADE.
- main gọi RiskManager theo giá ticker mỗi vòng; đồng thời đóng theo EMA21/RSI khi nến mới đóng.
- Random Forest/Predictor vẫn độc lập, chưa cấp tín hiệu cho main vì model chỉ phân lớp BUY/HOLD trong khi bot có LONG/SHORT.
- strategy_rules.json cung cấp nguyên tắc cho LLM; entry EMA9/EMA21 và RSI còn được Supervisor kiểm tra bằng Python.
- Supervisor từ chối action sai, lệnh ngược macro, thiếu cash, confidence thấp, sentiment thiếu hoặc sai schema.
- AgentTeam có sáu agent; Auditor chạy khi vòng lặp gặp exception. Sentiment cache 15 phút.

## LLM và cấu hình

- config.env.load_project_env nạp .env ở thư mục repo bất kể working directory; biến đã có trong process environment được ưu tiên. Settings và agent_team dùng chung loader. agent_team vẫn khởi tạo LLM client ở cấp module; Settings truyền vào AgentTeam không điều khiển _ask_llm.
- LLM_MODE=LOCAL mặc định dùng OpenAI-compatible endpoint http://localhost:11434/v1, qwen2.5:7b, timeout 45 giây.
- Mọi mode khác LOCAL dùng Cloud: Gemini trước, Groq dự phòng nếu có key. Model lấy từ GEMINI_MODEL và GROQ_FALLBACK_MODEL. Mỗi lần gọi sleep 0.3 giây, temperature 0.2.
- Parser hỗ trợ JSON thuần, markdown fence hoặc trích object đầu-cuối. Lỗi LLM trả dữ liệu dự phòng; không mặc định phản hồi luôn có action hợp lệ.
- Settings khai báo Binance spot, symbol/timeframe, vốn, sizing, phí, SL/TP/trailing, candle limit và loop interval. Tỷ lệ dùng dạng thập phân (0.01 = 1%).
- Không đọc/in/ghi giá trị bí mật trong .env hoặc đưa chúng vào prompt. Chỉ nhắc tên biến môi trường.

## Dữ liệu và thuật toán

- Fetcher trả timestamp epoch ms, OHLCV và datetime UTC. fetch_historical_ohlcv phân trang tối đa 1000 nến, khử trùng lặp, sắp xếp và bỏ nến cuối chưa chắc đã đóng. Các alias fetch khác chỉ tải một trang.
- add_indicators tính RSI14 bằng rolling mean gains/losses; MACD=EMA12-EMA26, signal=EMA9(MACD), EMA9, EMA21, ema_spread_pct=(EMA9-EMA21)/EMA21, volume_change=volume/rolling_mean_20-1; cuối cùng dropna.
- FEATURE_COLUMNS theo thứ tự: rsi_14, macd, macd_signal, ema_9, ema_21, ema_spread_pct, volume_change.
- preprocessor.create_buy_labels là helper riêng: mặc định xem 5 nến kế tiếp; BUY nếu high chạm +1.5% trước low chạm -1%; nếu cùng nến chạm cả hai thì ưu tiên stop; hàng cuối thiếu horizon là NA.
- train.py đọc storage/btc_5m.csv và dùng create_buy_labels: TP 1.5% trước SL 1% trong 5 nến. Chia theo thời gian 80/20, purge 5 mẫu giữa train/test. RandomForest: 250 cây, depth 8, min leaf 15, balanced, seed 42, n_jobs=-1; ghi đè models/model.pkl.
- Predictor lấy feature row mới nhất, BUY nếu P(BUY) >= 0.55, còn lại HOLD; thiếu model thì HOLD. Model chỉ có BUY/HOLD, không short.
- README mô tả hiện tại cách train.py gán nhãn TP/SL.

## PaperTrader và persistence

- RiskManager nhận cấu hình: mặc định sizing 10% cash, SL 1%, TP 2%, trailing gap 0.8%, kích hoạt sau lãi 1%. main kiểm tra LONG/SHORT theo ticker mỗi vòng.
- PaperTrader mặc định cash 100, fee_rate 0.0005 (0.05% mỗi chiều). Mở lệnh trừ stake; amount tính sau phí vào. PnL/cash sau đóng tính đủ hai phí; SHORT mô phỏng collateral và PnL, không gửi lệnh sàn.
- active_position.json lưu ledger gồm cash và vị thế, đồng thời đọc định dạng vị thế phẳng cũ để tương thích.
- PnL tạm tính và PnL khi đóng đã tính phí vào/ra; trades.csv được nối thêm khi đóng.
- runtime_state.json lưu nến cuối đã xử lý để tránh lặp quyết định sau restart.
- recent_closed_trades nằm trong RAM; Reflector evolve sau mỗi batch ba lệnh đóng trong phiên rồi xóa batch đã gửi.
- Reflector thêm lesson vào memory.json khi đóng. Khi có <=20 lesson, load_lessons trả toàn bộ; nhiều hơn thì lấy tối đa 10 khoản lỗ nặng nhất và 15 bài gần đây khớp side hoặc NONE, rồi bỏ trùng.
- auto_evolve_rules nhờ LLM tạo entry/exit rules; nếu có cả hai trường thì tăng version và lưu phả hệ strategy_rules.json. Operator đọc luật mỗi lần phân tích.

## Tác dụng phụ và dữ liệu cần giữ

- Coi storage/ và models/model.pkl là dữ liệu người dùng. Không xóa/reset/ghi đè nếu không được yêu cầu.
- migrate_rules.py ghi đè strategy_rules.json thành v8.
- fetch_and_save_dataset.py gọi Binance, mặc định tải 35.000 nến 5m rồi ghi đè storage/btc_5m.csv.
- test_system_flow.py gọi Binance, LLM, Fear & Greed/RSS và mở/đóng paper position, ghi active_position.json.
- train.py ghi đè model.pkl.
- main.py chạy liên tục và có thể gửi Discord; chỉ chạy khi người dùng yêu cầu.
- main.py kiểm tra hard SL/TP/trailing mỗi vòng, nhưng polling không bảo đảm bắt được spike ngắn hơn LOOP_SECONDS.
- .env.example là cấu hình mẫu không chứa khóa bí mật.
- requirements.txt khai báo ccxt, pandas, python-dotenv, joblib, requests, scikit-learn, openai và python-docx.

## Quy ước làm việc

- Đọc mã runtime trước README/comment/test/tài liệu sinh tự động; phân biệt tính năng đang chạy với thiết kế cũ hoặc chưa nối.
- Khi sửa bot, lần theo fetch -> features -> proposal -> review -> execution -> persistence. Giữ rõ paper trading và lệnh sàn thật.
- Nếu đổi thuật toán, đồng bộ label/training/inference khi cần; đừng mặc định ML đang cấp tín hiệu cho main.
- Đọc test_* trước khi chạy vì có thể gọi mạng hoặc sửa dữ liệu.
- Cập nhật file này khi kiến trúc hoặc hành vi runtime thay đổi đáng kể.

## ĐẶT BIỆT LƯU Ý
Agent KHÔNG ĐƯỢC PHÉP tự ý vận hành như một bot chạy thử nghiệm tự động. Để tiết kiệm token và giúp người dùng chủ động học tập, Agent phải tuân thủ nghiêm ngặt các điều sau:

1. **Tuyệt đối KHÔNG tự ý thực thi các lệnh chạy/kiểm tra kéo dài:**
   - CẤM tự ý chạy các script huấn luyện mô hình (ví dụ: `python src/train_qa.py`, fine-tuning loops).
   - CẤM chạy các lệnh lặp để theo dõi phần cứng hoặc tiến trình nền (ví dụ: `nvidia-smi`, kiểm tra CPU/RAM định kỳ).
   - CẤM tự ý chạy vòng lặp sửa lỗi - test lại liên tục trong terminal.

2. **Quy trình tương tác chuẩn (3 bước bắt buộc):**
   - **Bước 1 (Soạn thảo & Giải thích):** Tạo/chỉnh sửa file code cần thiết
   - **Bước 2 (Giao lệnh cho người dùng):** Cung cấp chính xác các câu lệnh PowerShell/Terminal để người dùng TỰ CHẠY trên máy cá nhân, kèm theo kết quả kỳ vọng (Expected Output).
   - **Bước 3 (Dừng lại & Đợi):** Ngừng sinh phản hồi ngay lập tức sau Bước 2. Chờ người dùng tự chạy, tự kiểm tra và dán kết quả hoặc thông báo lỗi vào thì mới được phản hồi tiếp.


# Crypto AI Paper Trader

Bot paper trading BTC/USDT trên Binance. Giá và nến lấy từ public API; bot không gửi lệnh thật. Quyết định vào lệnh cần qua điều kiện kỹ thuật, xu hướng 1H, kiểm duyệt rủi ro và sentiment. Stop-loss, take-profit, trailing stop và điều kiện đảo chiều EMA21/RSI được xử lý trong mã Python.

## Cài đặt

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Chỉnh `.env` để chọn local/cloud LLM và cấu hình paper account. Không commit `.env` hoặc API keys.

## Chạy paper bot

```powershell
python main.py
```

Vòng lặp kiểm tra giá hiện tại khoảng mỗi 15 giây để quản lý lệnh đang mở. Chỉ báo và tín hiệu được tính trên nến đã đóng của timeframe. Entry mặc định cần Operator đề xuất, confidence ít nhất 0.60, EMA9/EMA21 và RSI đồng thuận, không ngược chỉ thị 1H, sentiment khả dụng và Supervisor duyệt. Nếu dữ liệu 1H hoặc sentiment lỗi thì bot không mở lệnh mới; lệnh đang mở vẫn được quản lý bằng giá mới nhất.

Mặc định, vốn khởi tạo là 100 USDT, mỗi vị thế dùng 10% cash còn lại, phí mỗi chiều là 0.05%, stop-loss 1%, take-profit 2%, trailing stop cách đỉnh/đáy 0.8% sau khi lãi đạt 1%. Vị thế cũng đóng khi nến hoàn chỉnh phá EMA21 và RSI xác nhận đảo chiều. Các giá trị này cấu hình trong `.env` dưới dạng số thập phân (ví dụ 0.01 = 1%).

## Dữ liệu và huấn luyện

```powershell
python fetch_and_save_dataset.py
python train.py
```

Các lệnh trên gọi Binance và ghi dữ liệu; `train.py` ghi đè `models/model.pkl`. Dataset dùng nhãn BUY khi TP 1.5% xảy ra trước SL 1% trong 5 nến kế tiếp; nếu cùng một nến chạm cả hai mức, gán theo hướng thận trọng là SL trước. Tập test giữ theo thời gian và có purge 5 mẫu giữa train/test để tránh chồng lấn horizon.

Random Forest hiện là pipeline độc lập. `main.py` chưa dùng Predictor, vì vậy huấn luyện model chưa thay đổi quyết định của bot paper.

## Lưu trạng thái

- `storage/active_position.json`: cash và vị thế đang mở, được ghi nguyên tử để phục hồi sau restart.
- `storage/runtime_state.json`: thời điểm nến gần nhất đã xử lý, tránh xử lý lặp khi restart.
- `storage/trades.csv`: lịch sử lệnh đã đóng, PnL đã tính phí vào/ra.
- `storage/memory.json`, `storage/strategy_rules.json`: bài học và bộ quy tắc của Reflector.
- `storage/bot.log`: log vòng lặp.

Giữ nguyên các file này nếu chưa chủ ý reset paper account. `test_system_flow.py` có gọi mạng và ghi trạng thái giao dịch; đừng chạy như smoke test thuần offline. `migrate_rules.py` ghi đè bộ luật hiện tại.

## Giới hạn

Paper trading không mô phỏng trượt giá, khớp lệnh, funding hoặc độ trễ như sàn. Stop/trailing kiểm tra theo giá được lấy mỗi vòng lặp nên không bảo đảm bắt được biến động xảy ra giữa hai lần lấy giá. Vị thế SHORT chỉ là mô phỏng kế toán; endpoint đang dùng là Binance spot public data. Cần đánh giá bằng backtest/dry-run đủ dài trước khi cân nhắc thay đổi bất kỳ cơ chế nào.

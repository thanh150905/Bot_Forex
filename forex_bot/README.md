# Forex Trading Bot System

## Cấu trúc dự án

```
forex_bot/
├── license_server/          # Python FastAPI - Server chính
│   ├── main.py              # Entry point
│   ├── requirements.txt     # Dependencies
│   ├── core/
│   │   ├── config.py        # Cấu hình (SECRET_KEY, Telegram, etc.)
│   │   ├── database.py      # Models SQLAlchemy + init DB
│   │   └── security.py      # JWT + bcrypt
│   └── api/
│       ├── routes_auth.py   # Admin login, đổi mật khẩu
│       ├── routes_admin.py  # Quản lý user, license, IP
│       ├── routes_bot.py    # Bot verify, ping, report trade
│       └── routes_ai.py     # AI Engine: phân tích trend từ OHLCV
│
│   └── ai_engine/
│       ├── indicators.py    # EMA, ATR, RSI, Bollinger helpers
│       └── trend.py         # Classifier trend rule-based, ML-ready
│
├── bot_client/              # Bot C++ core + Python bridge
│   ├── bot_core.cpp         # C++ bot (strategy engine + pipe + license)
│   ├── json_simple.hpp      # JSON helper cho C++
│   ├── license_client.py    # Python license client (dùng nếu bot viết Python)
│   ├── mt5_ai_bot.py        # Python runtime kết nối MetaTrader5 + AI Engine
│   └── requirements_mt5.txt # Dependencies cho MT5 bot
│
└── mql5_ea/
    └── ForexBot_EA.mq5      # Expert Advisor cho MT4/MT5
```

---

## Bước 1 — Cài đặt License Server

Yêu cầu Python 3.11 hoặc 3.12. Không dùng Python 3.14 cho project này vì một số binary dependency của FastAPI/Pydantic có thể chưa có wheel tương thích.

```bash
cd license_server
pip install -r requirements.txt

# Đổi SECRET_KEY và mật khẩu admin trong core/config.py
# Hoặc dùng biến môi trường:
export SECRET_KEY="your_64_char_random_string"
export ADMIN_PASSWORD="YourStrongPassword123!"
export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
export TELEGRAM_ADMIN_CHAT_ID="your_chat_id"
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your_email@gmail.com"
export SMTP_PASSWORD="your_app_password"
export SMTP_FROM_EMAIL="your_email@gmail.com"
export SMTP_FROM_NAME="Forex Bot"

python main.py
# Server chạy tại http://localhost:8000
# Dashboard: http://localhost:8000/dashboard
# API docs:  http://localhost:8000/docs
```

---

## Bước 2 — Đăng nhập Admin

```bash
curl -X POST http://localhost:8000/auth/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@2024!Strong"}'
# → nhận được access_token
```

Dashboard admin:

```text
http://localhost:8000/dashboard
```

Cổng khách hàng:

```text
http://localhost:8000/user
```

User đăng ký bằng email + mật khẩu, nhận mã xác thực 6 số qua email rồi mới vào web và gửi tài khoản MT5.
Sau đó user đăng nhập bằng email + mật khẩu. Luồng quên mật khẩu cũng gửi mã reset qua email.
SMTP phải được cấu hình để user nhận mã thật trong hộp mail; với Gmail cần dùng App Password, không dùng mật khẩu Gmail thường.
Bạn có thể copy `license_server/.env.example` thành `license_server/.env`, điền SMTP rồi chạy lại server.

---

## Bước 3 — Tạo User + License thủ công (tuỳ chọn)

```bash
# Tạo user
curl -X POST http://localhost:8000/admin/users \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","email":"user1@gmail.com","note":"Khách hàng A"}'

# Tạo license cho user (user_id từ bước trên)
curl -X POST http://localhost:8000/admin/licenses \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":1}'
# → nhận license_key, giao cho user

# IP sẽ tự động lock khi bot kết nối lần đầu.
# Nếu muốn lock thủ công:
curl -X PATCH http://localhost:8000/admin/licenses/update-ip \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"license_key":"LICENSE_KEY_HERE","new_ip":"1.2.3.4"}'
```

---

## Bước 4 — Cài MT4/MT5 EA

1. Copy `ForexBot_EA.mq5` vào thư mục `MQL5/Experts/` của MetaTrader
2. Biên dịch trong MetaEditor (F7)
3. Kéo EA vào chart
4. Điền `LICENSE_KEY` và `SERVER_URL` trong input parameters
5. Cho phép WebRequest tới domain server trong MT4: Tools → Options → Expert Advisors

---

## Bước 5 — Chạy C++ Bot

```bash
# Cài libcurl (Ubuntu/Debian)
sudo apt install libcurl4-openssl-dev

# Compile
cd bot_client
g++ -std=c++17 -O2 bot_core.cpp -lcurl -o forex_bot

# Chạy
export LICENSE_KEY="YOUR_LICENSE_KEY"
export SERVER_URL="http://your-server:8000"
export MT_ACCOUNT="12345678"
./forex_bot
```

---

## Bước 6 — Chạy Python MT5 AI Bot

Bot này kết nối trực tiếp MetaTrader 5 terminal bằng Python package `MetaTrader5`, lấy nến thật, gọi `/ai/trend`, rồi gửi lệnh vào MT5. Mặc định chạy `DRY_RUN=true`, chỉ in tín hiệu, chưa vào lệnh thật.

Điều kiện:

- Dùng Windows
- Đã cài MetaTrader 5
- MT5 terminal đang mở và đã đăng nhập tài khoản
- License Server đang chạy tại `http://localhost:8000`
- Đã tạo user + license trên dashboard

MetaTrader5 Python package thường ổn định nhất với Python 3.11 trên Windows. Nếu `pip install MetaTrader5` báo không tìm thấy package trên Python 3.12/3.14, cài Python 3.11 rồi tạo venv lại cho riêng bot.

```powershell
cd C:\Users\trinh\Downloads\forex_bot_system\forex_bot\bot_client

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements_mt5.txt

$env:SERVER_URL="http://localhost:8000"
$env:LICENSE_KEY="LICENSE_KEY_DA_TAO"
$env:MT5_LOGIN="12345678"
$env:MT5_PASSWORD="YOUR_MT5_PASSWORD"
$env:MT5_SERVER="YOUR_BROKER_SERVER"
$env:SYMBOLS="EURUSD,XAUUSD"
$env:TIMEFRAME="M15"
$env:LOT_SIZE="0.01"
$env:DRY_RUN="true"

python mt5_ai_bot.py
```

Khi log tín hiệu ổn định trên demo, mới bật lệnh thật:

```powershell
$env:DRY_RUN="false"
python mt5_ai_bot.py
```

Các biến cấu hình chính:

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| SERVER_URL | http://localhost:8000 | License/API server |
| LICENSE_KEY | bắt buộc | License cấp từ dashboard |
| MT5_LOGIN | rỗng | Login tài khoản MT5, có thể bỏ trống nếu terminal đã đăng nhập |
| MT5_PASSWORD | rỗng | Mật khẩu tài khoản MT5 |
| MT5_SERVER | rỗng | Server broker, ví dụ Exness-MT5Real |
| SYMBOLS | EURUSD | Danh sách symbol, ngăn cách bằng dấu phẩy |
| TIMEFRAME | M1 | M1/M5/M15/M30/H1/H4/D1 |
| ENSEMBLE_TIMEFRAMES | M1,M5,M15 | Danh sách timeframe để gom phiếu tín hiệu |
| MIN_ENSEMBLE_AGREEMENT | 2 | Số timeframe tối thiểu phải đồng thuận BUY/SELL |
| STRATEGY | scalping | scalping = EMA 5/13/34 impulse; trend = EMA/RSI trend engine |
| LOT_SIZE | 0.01 | Lot cố định |
| DRY_RUN | true | true = không vào lệnh thật |
| MIN_CONFIDENCE | 0.68 | AI confidence tối thiểu để vào lệnh |
| MIN_WIN_PROBABILITY | 0.58 | Xác suất ước tính tối thiểu để mở lệnh |
| MAX_SIGNAL_RISK | 0.55 | Điểm rủi ro tín hiệu tối đa; thấp hơn là tốt hơn |
| MAX_SPREAD_POINTS | 30 | Bỏ qua nếu spread quá cao |
| LOOP_SECONDS | 3 | Chu kỳ quét tín hiệu |
| MAX_POSITIONS_PER_SYMBOL | 4 | Số lệnh bot được mở cùng lúc trên mỗi symbol |
| MAX_TOTAL_POSITIONS | 6 | Tổng số lệnh bot được mở cùng lúc trên toàn bộ symbol |
| ALLOW_HEDGING | true | Cho phép giữ BUY và SELL cùng symbol nếu tài khoản broker hỗ trợ hedge |
| MIN_ORDER_SPACING_SECONDS | 20 | Khoảng cách tối thiểu giữa hai lệnh cùng symbol |
| MIN_ADD_CONFIDENCE | 0.78 | Confidence tối thiểu để nhồi thêm lệnh cùng chiều |
| PYRAMID_LOT_MULTIPLIER | 0.70 | Lot của lệnh nhồi sau nhỏ dần theo hệ số này |
| MAX_EQUITY_DRAWDOWN_PERCENT | 4 | Dừng mở lệnh mới khi equity drawdown chạm ngưỡng |
| MAX_DAILY_LOSS_PERCENT | 3 | Dừng mở lệnh mới khi lỗ đã đóng trong ngày chạm ngưỡng |
| MAX_SYMBOL_FLOATING_LOSS | 0 | Dừng mở lệnh mới nếu lỗ nổi symbol vượt số tiền này; 0 = tắt |
| CLOSE_ON_REVERSE | false | true = đóng lệnh ngược; false = cho phép hedge theo `ALLOW_HEDGING` |
| MAX_HOLD_SECONDS | 600 | Tự đóng lệnh scalping nếu giữ quá số giây này; 0 = tắt |
| BREAKEVEN_POINTS | 80 | Khi lời đủ points, kéo SL về entry |
| TRAILING_START_POINTS | 120 | Khi lời đủ points, bật trailing stop |
| TRAILING_DISTANCE_POINTS | 80 | Khoảng cách trailing stop tính theo points |
| NEWS_FILTER_ENABLED | true | Bật lọc tin tức mạnh trước khi mở lệnh mới |
| NEWS_BLOCK_BEFORE_MINUTES | 45 | Không mở lệnh trước tin mạnh N phút |
| NEWS_BLOCK_AFTER_MINUTES | 20 | Không mở lệnh sau tin mạnh N phút |
| NEWS_IMPACTS | High,Holiday | Impact bị chặn từ calendar |
| NEWS_FAIL_CLOSED | false | true = nếu nguồn tin lỗi thì dừng mở lệnh; false = cảnh báo rồi vẫn chạy |
| MAGIC | 260501 | Magic number để nhận diện lệnh của bot |
| MT5_PATH | rỗng | Đường dẫn terminal64.exe nếu cần chỉ định |

Trade mở/đóng thành công sẽ được report về server qua `/bot/report-trade`, hiển thị trong dashboard, hiện Live Notifications trên web và gửi Telegram nếu đã cấu hình token.

### News Filter

Server dùng Forex Factory/FairEconomy weekly JSON export:

```text
https://nfs.faireconomy.media/ff_calendar_thisweek.json
```

Bot gọi `/ai/news-risk` trước khi mở lệnh. Nếu symbol bị ảnh hưởng bởi `High` hoặc `Holiday` news trong cửa sổ cấu hình, bot sẽ bỏ qua lệnh mới. Với `XAUUSD`, bộ lọc mặc định xem như chịu ảnh hưởng bởi USD news.

Nguồn export này có giới hạn request, nên server cache mặc định 1 giờ và không để từng chart/EA tải trực tiếp.

### Backtest Offline

Chuẩn bị CSV có cột:

```text
time,open,high,low,close,volume
```

Chạy:

```powershell
cd C:\Users\trinh\Downloads\forex_bot_system\forex_bot\bot_client
python backtest_strategy.py --csv data\XAUUSDm_M1.csv --strategy scalping --bars 100 --point 0.01 --spread-points 300
```

Kết quả trả về số lệnh, win rate, net points, profit factor và max drawdown points. Đây là backtest rule-based đơn giản để lọc cấu hình trước khi chạy demo/live.

---

## API Endpoints Tổng Quan

| Method | URL | Mô tả |
|--------|-----|-------|
| POST | /auth/admin/login | Admin đăng nhập |
| GET  | /admin/dashboard | Tổng quan hệ thống |
| GET  | /admin/users | Danh sách user |
| POST | /admin/users | Tạo user mới |
| PATCH| /admin/users/{id} | Cập nhật user |
| GET  | /admin/licenses | Danh sách license |
| POST | /admin/licenses | Tạo license |
| PATCH| /admin/licenses/update-ip | Cập nhật/reset IP |
| DELETE| /admin/licenses/{key} | Thu hồi license |
| GET  | /admin/bots | Trạng thái bot theo license: online/offline/never connected |
| POST | /admin/ai/trend | Admin test AI trend trên dashboard |
| POST | /admin/web-bot/paper-trade | Ghi lệnh paper từ Web AI Bot |
| GET  | /admin/sessions | Log kết nối bot |
| GET  | /admin/trades | Lịch sử giao dịch |
| POST | /bot/verify | Bot xác thực license |
| POST | /bot/ping | Bot ping định kỳ |
| POST | /bot/report-trade | Bot báo cáo lệnh |
| POST | /ai/trend | AI Engine phân tích trend và trả BUY/SELL/HOLD |

Dashboard web có sẵn tại `http://localhost:8000/dashboard`. Giao diện này dùng trực tiếp các API admin để đăng nhập, xem tổng quan, chạy Web AI Bot paper mode, xem bot online/offline, tạo user, tạo license, reset IP, thu hồi license, xem sessions và trades.

---

## AI Engine API

Sau khi bot xác thực bằng `/bot/verify`, dùng `bot_token` để gọi AI Engine:

```bash
curl -X POST http://localhost:8000/ai/trend \
  -H "Content-Type: application/json" \
  -d '{
    "bot_token": "BOT_TOKEN_FROM_VERIFY",
    "license_key": "LICENSE_KEY_HERE",
    "symbol": "EURUSD",
    "timeframe": "M15",
    "candles": [
      {"open":1.0800,"high":1.0810,"low":1.0790,"close":1.0805}
    ]
  }'
```

Ví dụ trên rút gọn phần `candles`; request thật cần tối thiểu 60 nến. Response trả về:

```json
{
  "trend": "trending_up",
  "signal": "BUY",
  "confidence": 0.9,
  "entry_price": 1.0852,
  "sl_price": 1.0821,
  "tp_price": 1.0894,
  "indicators": {
    "ema_8": 1.0848,
    "ema_21": 1.0833,
    "ema_50": 1.0819,
    "atr_14": 0.0021,
    "rsi_14": 61.2
  }
}
```

Hiện tại engine dùng rule-based scoring từ EMA/ATR/RSI/Bollinger để chạy nhẹ trong FastAPI. Khi có dữ liệu trade đủ lớn, có thể thay phần scoring trong `ai_engine/trend.py` bằng LightGBM/scikit-learn mà giữ nguyên contract API cho C++ bot.

---

## Luồng bảo mật IP

```
Bot khởi động
    ↓
Gửi license_key + IP thực lên /bot/verify
    ↓
[Lần đầu] IP chưa lock → Server tự lock IP đó
[Lần sau] IP khớp → OK, cấp token
[IP khác] → Từ chối + Alert Telegram cho admin
    ↓
Bot nhận JWT token (6 giờ)
    ↓
Ping mỗi 5 phút → Gia hạn token
Bot không ping trong 10 phút → Alert admin
```

---

## Lưu ý bảo mật

- Đổi `SECRET_KEY` ngay sau khi cài (dùng `openssl rand -hex 32`)
- Đổi `ADMIN_PASSWORD` ngay lần đầu đăng nhập
- Deploy server trên HTTPS (dùng Nginx + Let's Encrypt)
- Không commit file `.env` lên Git
- Backup file `forex_license.db` định kỳ

---

## Roadmap tiếp theo

- [x] **AI Engine v1**: REST API phân tích xu hướng bằng EMA/ATR/RSI/Bollinger
- [ ] **AI Engine v2**: Python ML model phân tích xu hướng
- [ ] **News Filter**: Lọc tin Forex Factory
- [ ] **Web Dashboard**: React + TradingView charts
- [ ] **Mobile App**: Flutter
- [ ] **Chiến lược C++**: Thêm RSI, Bollinger, Volume filter

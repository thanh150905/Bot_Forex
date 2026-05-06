# Copy file này thành run_mt5_bot.ps1 rồi điền thông tin thật.
# Chạy trong PowerShell tại thư mục forex_bot\bot_client.

$env:SERVER_URL = "http://localhost:8000"
$env:LICENSE_KEY = "LICENSE_KEY_DA_TAO_TREN_DASHBOARD"

# Thông tin tài khoản MetaTrader 5.
# Nếu MT5 terminal đã mở và đã đăng nhập sẵn, có thể để trống 3 dòng này.
$env:MT5_LOGIN = "12345678"
$env:MT5_PASSWORD = "YOUR_MT5_PASSWORD"
$env:MT5_SERVER = "YOUR_BROKER_SERVER"

# Nếu máy có nhiều MT5 terminal, điền đúng đường dẫn terminal64.exe.
# $env:MT5_PATH = "C:\Program Files\MetaTrader 5\terminal64.exe"

$env:SYMBOLS = "EURUSD"
$env:TIMEFRAME = "M1"
$env:ENSEMBLE_TIMEFRAMES = "M1,M5,M15"
$env:MIN_ENSEMBLE_AGREEMENT = "2"
$env:STRATEGY = "scalping"
$env:BARS = "100"
$env:LOT_SIZE = "0.01"
$env:MIN_CONFIDENCE = "0.68"
$env:MIN_WIN_PROBABILITY = "0.58"
$env:MAX_SIGNAL_RISK = "0.55"
$env:MAX_SPREAD_POINTS = "30"
$env:LOOP_SECONDS = "3"

# Quản lý nhiều lệnh scalping: cho phép BUY/SELL cùng symbol nếu tài khoản hedge hỗ trợ.
$env:MAX_POSITIONS_PER_SYMBOL = "4"
$env:MAX_TOTAL_POSITIONS = "6"
$env:ORDERS_PER_SIGNAL = "3"
$env:BATCH_MIN_CONFIDENCE = "0.82"
$env:ALLOW_HEDGING = "true"
$env:MIN_ORDER_SPACING_SECONDS = "20"
$env:MIN_ADD_CONFIDENCE = "0.78"
$env:BATCH_FIXED_LOT = "true"
$env:PYRAMID_LOT_MULTIPLIER = "1.00"

# Chốt rủi ro tài khoản. Bot dừng mở lệnh mới khi chạm ngưỡng này.
$env:MAX_EQUITY_DRAWDOWN_PERCENT = "4"
$env:MAX_DAILY_LOSS_PERCENT = "3"
$env:MAX_SYMBOL_FLOATING_LOSS = "0"

# Quản lý lệnh đang mở: đóng nhanh khi đảo chiều, hòa vốn và trailing stop.
$env:CLOSE_ON_REVERSE = "false"
$env:MAX_HOLD_SECONDS = "600"
$env:BREAKEVEN_POINTS = "80"
$env:TRAILING_START_POINTS = "120"
$env:TRAILING_DISTANCE_POINTS = "80"

# Lọc tin tức mạnh bằng Forex Factory/FairEconomy calendar export.
$env:NEWS_FILTER_ENABLED = "true"
$env:NEWS_BLOCK_BEFORE_MINUTES = "45"
$env:NEWS_BLOCK_AFTER_MINUTES = "20"
$env:NEWS_IMPACTS = "High,Holiday"
$env:NEWS_FAIL_CLOSED = "false"

# true = test tín hiệu, không vào lệnh thật.
# false = gửi order thật vào MT5.
$env:DRY_RUN = "true"

python mt5_ai_bot.py

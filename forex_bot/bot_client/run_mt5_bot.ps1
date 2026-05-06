# ============================================================
#  run_mt5_bot.ps1  —  M1 scalp cycle candidate
#  v3.1 — M1 execution, M5 confirmation, fast hedge cycle, profit recycle
#  Chiến lược: M1 scalp XAU/ETH/BTC, BUY/SELL có kiểm soát
#  Chỉnh sửa thông tin tài khoản trước khi chạy.
#  Khuyến nghị: test DRY_RUN=true ít nhất 3–5 ngày trước live.
# ============================================================

# ------------------------------------------------------------------
# [1] KẾT NỐI SERVER & LICENSE
# ------------------------------------------------------------------
$env:SERVER_URL  = "http://localhost:8000"
$env:LICENSE_KEY = "05BC258B9CC14C8599BF159BE731B277"

# ------------------------------------------------------------------
# [2] TÀI KHOẢN METATRADER 5
#     Nếu terminal đã mở và đã đăng nhập sẵn → để trống 3 dòng này.
#     CẢNH BÁO BẢO MẬT: Không commit file này lên Git/public repo.
# ------------------------------------------------------------------
$env:MT5_LOGIN    = "415620293"
$env:MT5_PASSWORD = "Thanh150905@"
$env:MT5_SERVER   = "Exness-MT5Trial14"

# Nếu máy có nhiều MT5 terminal, bỏ comment và điền đúng đường dẫn:
# $env:MT5_PATH = "C:\Program Files\MetaTrader 5\terminal64.exe"

# ------------------------------------------------------------------
# [3] SYMBOL & KHUNG THỜI GIAN
# ------------------------------------------------------------------
# Đổi đúng 1 dòng này để chuyển nhanh:
#   XAU    = chỉ XAUUSDm
#   ETH    = chỉ ETHUSDm
#   BTC    = chỉ BTCUSDm
#   CRYPTO = ETHUSDm,BTCUSDm
#   ALL    = XAUUSDm,ETHUSDm,BTCUSDm
$SYMBOL_MODE = "XAU"
# $SYMBOL_MODE = "BTC"


$selectedSymbols = "XAUUSDm"
$selectedLotSize = "0.01"
$selectedMaxSpreadPoints = "350"
$selectedTradeSessionsUtc = "00:00-23:59"
$selectedMaxTotalPositions = "10"

switch ($SYMBOL_MODE.ToUpper()) {
    "XAU" {
        $selectedSymbols = "XAUUSDm"
        $selectedLotSize = "0.01"
        $selectedMaxSpreadPoints = "350"
        $selectedTradeSessionsUtc = "00:00-23:59"
        $selectedMaxTotalPositions = "10"
    }
    "ETH" {
        $selectedSymbols = "ETHUSDm"
        $selectedLotSize = "0.01"
        $selectedMaxSpreadPoints = "5000"
        $selectedTradeSessionsUtc = "00:00-23:59"
        $selectedMaxTotalPositions = "10"
    }
    "BTC" {
        $selectedSymbols = "BTCUSDm"
        $selectedLotSize = "0.01"
        $selectedMaxSpreadPoints = "20000"
        $selectedTradeSessionsUtc = "00:00-23:59"
        $selectedMaxTotalPositions = "10"
    }
    "CRYPTO" {
        $selectedSymbols = "ETHUSDm,BTCUSDm"
        $selectedLotSize = "0.01"
        $selectedMaxSpreadPoints = "20000"
        $selectedTradeSessionsUtc = "00:00-23:59"
        $selectedMaxTotalPositions = "20"
    }
    "ALL" {
        $selectedSymbols = "XAUUSDm,ETHUSDm,BTCUSDm"
        $selectedLotSize = "0.01"
        $selectedMaxSpreadPoints = "20000"
        $selectedTradeSessionsUtc = "00:00-23:59"
        $selectedMaxTotalPositions = "30"
    }
    default {
        throw "SYMBOL_MODE không hợp lệ: $SYMBOL_MODE. Dùng XAU, ETH, BTC, CRYPTO hoặc ALL."
    }
}

$env:SYMBOLS              = $selectedSymbols
$env:TIMEFRAME            = "M1"
$env:ENSEMBLE_TIMEFRAMES  = "M1"
$env:MIN_ENSEMBLE_AGREEMENT = "1"       # M1 scalp vào theo tín hiệu M1; M5 confirmation sẽ làm bot HOLD nhiều hơn
$env:STRATEGY             = "scalping"
$env:BARS                 = "120"

# ------------------------------------------------------------------
# [4] KÍCH THƯỚC LỆNH
# ------------------------------------------------------------------
$env:LOT_SIZE             = $selectedLotSize

# ------------------------------------------------------------------
# [5] NGƯỠNG TÍN HIỆU  ← SIẾT LẠI ĐỂ GIẢM EXPECTANCY ÂM
#
#   Các ngưỡng dưới đây được siết để bot bỏ qua setup yếu và spread đắt.
# ------------------------------------------------------------------
$env:MIN_CONFIDENCE       = "0.55"
$env:MIN_WIN_PROBABILITY  = "0.53"
$env:MAX_SIGNAL_RISK      = "0.55"
$env:MAX_SPREAD_POINTS    = $selectedMaxSpreadPoints
$env:MAX_SPREAD_ATR_RATIO = "0.25"  # Spread không được ăn quá nhiều biên ATR của setup
$env:MIN_TP_SPREAD_RATIO  = "2.50"  # TP dự kiến phải lớn hơn spread ít nhất 2.5 lần

# Tốc độ vòng lặp — M1 cần phản ứng nhanh; chế độ hedge-pair cho phép vào nối tiếp.
$env:LOOP_SECONDS         = "1"
$env:COMMAND_POLL_SECONDS = "2"    # Admin web Control gửi pause/resume/close/config xuống bot

# Chạy 24/7 theo yêu cầu vận hành. Giờ UTC; đặt 00:00-23:59 để không khóa phiên.
$env:TRADE_SESSION_ENABLED = "true"
$env:TRADE_SESSIONS_UTC    = $selectedTradeSessionsUtc
$env:ONE_TRADE_PER_BAR     = "false"
$env:REENTRY_COOLDOWN_SECONDS = "0"

# ------------------------------------------------------------------
# [6] QUẢN LÝ LỆNH  ← M1 SCALP: CÓ BUY/SELL, KHÔNG BATCH
#
#   Không nhân lệnh cùng chiều. Nếu muốn scale sau này, chỉ tăng khi backtest
#   và forward test có profit factor đủ tốt.
# ------------------------------------------------------------------
$env:MAX_POSITIONS_PER_SYMBOL    = "10"
$env:MAX_TOTAL_POSITIONS         = $selectedMaxTotalPositions
$env:ORDERS_PER_SIGNAL           = "1"
$env:BATCH_MIN_CONFIDENCE        = "0.68"
$env:FORCE_BOTH_SIDES            = "false"
$env:FORCE_ALTERNATE_SIDES       = "true"
$env:FORCE_ENTRY_CONFIDENCE      = "0.70"

# Lọc trạng thái thị trường bằng ADX/DMI:
# - SIDEWAY: ADX < ADX_SIDEWAY_LEVEL.
# - UPTREND/DOWNTREND: chỉ cho lệnh thuận xu hướng nếu TREND_FILTER_ENABLED=true.
$env:ADX_PERIOD                  = "14"
$env:ADX_SIDEWAY_LEVEL           = "25.0"
$env:TREND_FILTER_ENABLED        = "true"

$env:ALLOW_HEDGING               = "true"
$env:MIN_ORDER_SPACING_SECONDS   = "0"
$env:MIN_ADD_CONFIDENCE          = "0.70"
$env:BATCH_FIXED_LOT             = "true"
$env:PYRAMID_LOT_MULTIPLIER      = "1.00"
$env:LOT_MIN_SIZE                = "0"
$env:LOT_MAX_SIZE                = "0"
$env:LOT_STEP_SIZE               = "0"
$env:TREND_LOT_MULTIPLIER        = "1.00"
$env:SIDEWAY_LOT_MULTIPLIER      = "1.00"
$env:COUNTER_TREND_LOT_MULTIPLIER = "0.50"

# ------------------------------------------------------------------
# [7] GIỚI HẠN RỦI RO TÀI KHOẢN
#
#   Các giới hạn này dùng để dừng mở lệnh mới khi bot đi sai trạng thái.
# ------------------------------------------------------------------
$env:MAX_EQUITY_DRAWDOWN_PERCENT = "4"
$env:MAX_DAILY_LOSS_PERCENT      = "3"
$env:MAX_SYMBOL_FLOATING_LOSS    = "40"

# ------------------------------------------------------------------
# [8] QUẢN LÝ LỆNH ĐANG MỞ
#
#   Mỗi lệnh lời >= 2$ thì đóng riêng. Tổng basket lời >= 10$ thì đóng tất cả.
# ------------------------------------------------------------------
$env:CLOSE_ON_REVERSE            = "false"
$env:MAX_HOLD_SECONDS            = "600"
$env:CLOSE_LOSERS_ENABLED        = "true"
$env:LOSER_MAX_LOSS_MONEY        = "40.00"
$env:LOSER_MAX_LOSS_POINTS       = "0"
$env:CLOSE_WINNERS_ENABLED       = "true"
$env:WINNER_MIN_PROFIT_MONEY     = "3.00"
$env:WINNER_MAX_PROFIT_MONEY     = "8.00"
$env:WINNER_MIN_PROFIT_POINTS    = "0"
$env:BASKET_CLOSE_ENABLED        = "true"
$env:BASKET_MIN_CLOSE_POSITIONS  = "0"
$env:BASKET_MIN_NET_PROFIT_MONEY = "50.00"
$env:BASKET_MAX_NET_LOSS_MONEY   = "40.00"
$env:BASKET_PROFIT_LOSS_RATIO    = "0"
$env:BREAKEVEN_POINTS            = "90"
$env:TRAILING_START_POINTS       = "120"
$env:TRAILING_DISTANCE_POINTS    = "70"

# ------------------------------------------------------------------
# [9] LỌC TIN TỨC
#
#   Lỗi "[NEWS] filter failed, fail-open: Not Found" xảy ra do:
#   - Bot server (localhost:8000) không fetch được lịch Forex Factory
#   - Hoặc endpoint news chưa được cấu hình trên server
#
#   Nếu endpoint news chưa reload hoặc nguồn lịch lỗi, fail-open để bot không bị khóa cứng.
#   Khi server đã chắc chắn có /ai/news-risk ổn định, có thể đổi NEWS_FAIL_CLOSED=true.
#
#   Khung giờ có tin mạnh XAUUSD thường gặp (giờ Việt Nam):
#     15:30–16:00  : Số liệu Mỹ (CPI, NFP, GDP, Retail Sales...)
#     21:00–22:00  : Fed meeting / Powell speech
#     Thứ 6 20:30  : Non-Farm Payrolls (tránh cả ngày)
#   → Nên tắt bot thủ công trong các khung giờ này khi NEWS_FILTER_ENABLED=false
# ------------------------------------------------------------------
$env:NEWS_FILTER_ENABLED         = "false"
$env:NEWS_BLOCK_BEFORE_MINUTES   = "45"
$env:NEWS_BLOCK_AFTER_MINUTES    = "20"
$env:NEWS_IMPACTS                = "High,Holiday"
$env:NEWS_FAIL_CLOSED            = "false"

# ------------------------------------------------------------------
# [10] CHẾ ĐỘ CHẠY
#
#   DRY_RUN = true  → Chỉ test tín hiệu, KHÔNG vào lệnh thật
#   DRY_RUN = false → Gửi lệnh thật vào MT5
#
#   KHUYẾN NGHỊ: Giữ true cho đến khi xác nhận win rate > 57%
#   sau ít nhất 3–5 ngày dry run. Sau đó mới đổi sang false.
# ------------------------------------------------------------------
$env:DRY_RUN = "false"

# ------------------------------------------------------------------
# KHỞI CHẠY BOT
# ------------------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MT5 AI Bot — M1 Scalp Cycle v3.1" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Symbol Mode  : $SYMBOL_MODE" -ForegroundColor White
Write-Host "Symbol       : $env:SYMBOLS" -ForegroundColor White
Write-Host "Strategy     : $env:STRATEGY ($env:TIMEFRAME)" -ForegroundColor White
Write-Host "Lot Size     : $env:LOT_SIZE" -ForegroundColor White
Write-Host "Confidence   : $env:MIN_CONFIDENCE" -ForegroundColor White
Write-Host "Max Pos      : $env:MAX_TOTAL_POSITIONS total / $env:MAX_POSITIONS_PER_SYMBOL per symbol" -ForegroundColor White
Write-Host "Hedging      : $env:ALLOW_HEDGING" -ForegroundColor White
Write-Host "Max Spread   : $env:MAX_SPREAD_POINTS pts (London/NY tốt nhất để scalp)" -ForegroundColor White
Write-Host "Session UTC  : $env:TRADE_SESSIONS_UTC" -ForegroundColor White
Write-Host "Web Control  : poll mỗi $env:COMMAND_POLL_SECONDS giây" -ForegroundColor White
Write-Host "News Filter  : $env:NEWS_FILTER_ENABLED (fail closed: $env:NEWS_FAIL_CLOSED)" -ForegroundColor White
Write-Host "Drawdown Lim : $env:MAX_EQUITY_DRAWDOWN_PERCENT% equity / $env:MAX_DAILY_LOSS_PERCENT% daily" -ForegroundColor White
Write-Host ""

if ($env:DRY_RUN -eq "true") {
    Write-Host "[DRY RUN MODE] Không vào lệnh thật — chỉ test tín hiệu" -ForegroundColor Yellow
    Write-Host "Sau 3-5 ngày: xem win rate, nếu > 57% thì đổi DRY_RUN=false" -ForegroundColor Yellow
} else {
    Write-Host "[LIVE MODE] Đang gửi lệnh THẬT vào MT5!" -ForegroundColor Red
    Write-Host "Đảm bảo bạn đã kiểm tra dry run trước." -ForegroundColor Red
}

Write-Host ""
python mt5_ai_bot.py

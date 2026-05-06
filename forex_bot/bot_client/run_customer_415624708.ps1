# Chạy file này trên máy khách có IP public 113.22.248.28.
# MT5 phải mở sẵn, đăng nhập đúng account 415624708, và bật Algo Trading.

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Set-Location $PSScriptRoot

$LogDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LatestLog = Join-Path $LogDir "customer_415624708_latest.log"
$HistoryLog = Join-Path $LogDir "customer_415624708_$Stamp.log"
Remove-Item -Path $LatestLog -Force -ErrorAction SilentlyContinue

function Write-Step {
    param([string]$Message)
    $Line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    $Line | Tee-Object -FilePath $LatestLog -Append | Tee-Object -FilePath $HistoryLog -Append
}

function Stop-WithError {
    param([string]$Message)
    Write-Step "[LOI] $Message"
    Write-Step "Xem log: $LatestLog"
    exit 1
}

$env:SERVER_URL  = "https://marget-sacerdotal-sonny.ngrok-free.dev"
$env:LICENSE_KEY = "1F2903BE005E4345A22145340E622177"

$env:MT_ACCOUNT   = "415624708"
$env:MT5_LOGIN    = "415624708"
$env:MT5_PASSWORD = ""
$env:MT5_SERVER   = "Exness-MT5Trial14"

$env:SYMBOLS = "XAUUSDm"
$env:TIMEFRAME = "M1"
$env:ENSEMBLE_TIMEFRAMES = "M1"
$env:MIN_ENSEMBLE_AGREEMENT = "1"
$env:STRATEGY = "scalping"
$env:BARS = "120"

$env:LOT_SIZE = "0.01"
$env:LOT_MIN_SIZE = "0"
$env:LOT_MAX_SIZE = "0"
$env:LOT_STEP_SIZE = "0"
$env:TREND_LOT_MULTIPLIER = "1.00"
$env:SIDEWAY_LOT_MULTIPLIER = "1.00"
$env:COUNTER_TREND_LOT_MULTIPLIER = "0.50"
$env:BATCH_FIXED_LOT = "true"
$env:PYRAMID_LOT_MULTIPLIER = "1.00"

$env:LOOP_SECONDS = "1"
$env:COMMAND_POLL_SECONDS = "2"
$env:TRADE_SESSION_ENABLED = "true"
$env:TRADE_SESSIONS_UTC = "00:00-23:59"
$env:ONE_TRADE_PER_BAR = "false"
$env:REENTRY_COOLDOWN_SECONDS = "0"

$env:MIN_CONFIDENCE = "0.55"
$env:MIN_WIN_PROBABILITY = "0.53"
$env:MAX_SIGNAL_RISK = "0.55"
$env:MAX_SPREAD_POINTS = "350"
$env:MAX_SPREAD_ATR_RATIO = "0.18"
$env:MIN_TP_SPREAD_RATIO = "2.50"

$env:MAX_POSITIONS_PER_SYMBOL = "10"
$env:MAX_TOTAL_POSITIONS = "10"
$env:ORDERS_PER_SIGNAL = "1"
$env:BATCH_MIN_CONFIDENCE = "0.68"
$env:FORCE_BOTH_SIDES = "false"
$env:FORCE_ALTERNATE_SIDES = "true"
$env:TREND_FILTER_ENABLED = "true"
$env:ALLOW_HEDGING = "true"
$env:MIN_ORDER_SPACING_SECONDS = "0"
$env:MIN_ADD_CONFIDENCE = "0.78"

$env:MAX_EQUITY_DRAWDOWN_PERCENT = "4"
$env:MAX_DAILY_LOSS_PERCENT = "3"
$env:MAX_SYMBOL_FLOATING_LOSS = "40"
$env:CLOSE_ON_REVERSE = "false"
$env:MAX_HOLD_SECONDS = "600"
$env:CLOSE_LOSERS_ENABLED = "true"
$env:LOSER_MAX_LOSS_MONEY = "40.00"
$env:LOSER_MAX_LOSS_POINTS = "0"
$env:CLOSE_WINNERS_ENABLED = "true"
$env:WINNER_MIN_PROFIT_MONEY = "3.00"
$env:WINNER_MAX_PROFIT_MONEY = "8.00"
$env:WINNER_MIN_PROFIT_POINTS = "0"
$env:BASKET_CLOSE_ENABLED = "true"
$env:BASKET_MIN_CLOSE_POSITIONS = "0"
$env:BASKET_MIN_NET_PROFIT_MONEY = "50.00"
$env:BASKET_MAX_NET_LOSS_MONEY = "40.00"
$env:BASKET_PROFIT_LOSS_RATIO = "0"

$env:NEWS_FILTER_ENABLED = "false"
$env:NEWS_FAIL_CLOSED = "false"
$env:DRY_RUN = "false"
$env:PYTHONUNBUFFERED = "1"
$env:CUSTOMER_WATCHDOG_POLL_SECONDS = "5"
$env:CUSTOMER_BOT_RESTART_SECONDS = "10"

Write-Step "=== Bat dau chay bot customer 415624708 ==="
Write-Step "Server: $env:SERVER_URL"
Write-Step "MT5 login: $env:MT5_LOGIN | Server: $env:MT5_SERVER | Symbol: $env:SYMBOLS"

try {
    $Health = Invoke-RestMethod -Uri "$env:SERVER_URL/health" -TimeoutSec 10
    Write-Step "[OK] Ket noi license server: $($Health.status)"
} catch {
    Write-Step "[CANH BAO] PowerShell chua ket noi duoc server: $($_.Exception.Message). Se kiem tra lai bang Python."
}

try {
    $PublicIp = (Invoke-RestMethod -Uri "https://api.ipify.org?format=text" -TimeoutSec 10).Trim()
    Write-Step "Public IP may khach: $PublicIp"
    if ($PublicIp -ne "113.22.248.28") {
        Write-Step "[CANH BAO] IP hien tai khac IP license 113.22.248.28. Neu bot bi reject IP, can cap nhat IP license."
    }
} catch {
    Write-Step "[CANH BAO] Khong doc duoc public IP: $($_.Exception.Message)"
}

$VenvDir = Join-Path $PSScriptRoot ".venv_customer_415624708"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
if (!(Test-Path $PythonExe)) {
    Write-Step "Tao Python venv rieng cho may khach..."
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & py -3.11 -m venv $VenvDir 2>&1 | Tee-Object -FilePath $LatestLog -Append | Tee-Object -FilePath $HistoryLog -Append
    } else {
        $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if (!$PythonCmd) {
            Stop-WithError "Khong tim thay Python. Cai Python 3.11 roi chay lai file nay."
        }
        & python -m venv $VenvDir 2>&1 | Tee-Object -FilePath $LatestLog -Append | Tee-Object -FilePath $HistoryLog -Append
    }
}

if (!(Test-Path $PythonExe)) {
    Stop-WithError "Khong tao duoc venv Python: $VenvDir"
}

Write-Step "Python: $PythonExe"
& $PythonExe -c "import httpx, MetaTrader5 as mt5; print('deps ok')" 2>&1 | Tee-Object -FilePath $LatestLog -Append | Tee-Object -FilePath $HistoryLog -Append
if ($LASTEXITCODE -ne 0) {
    Write-Step "Cai thu vien MetaTrader5/httpx..."
    & $PythonExe -m pip install -r requirements_mt5.txt 2>&1 | Tee-Object -FilePath $LatestLog -Append | Tee-Object -FilePath $HistoryLog -Append
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError "Cai thu vien that bai. Gui file log latest cho admin."
    }
}

& $PythonExe -c "import httpx, MetaTrader5 as mt5; print('deps ok')" 2>&1 | Tee-Object -FilePath $LatestLog -Append | Tee-Object -FilePath $HistoryLog -Append
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "Thieu thu vien Python sau khi cai dat. Gui file log latest cho admin."
}

& $PythonExe -c "import os, httpx; r=httpx.get(os.environ['SERVER_URL'] + '/health', timeout=10); print('server health', r.status_code, r.text); r.raise_for_status()" 2>&1 | Tee-Object -FilePath $LatestLog -Append | Tee-Object -FilePath $HistoryLog -Append
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "Python khong ket noi duoc license server qua ngrok. Kiem tra mang/firewall/ngrok URL."
}

if ([string]::IsNullOrWhiteSpace($env:MT5_PASSWORD)) {
    Write-Step "[LUU Y] MT5_PASSWORD dang trong. May khach phai mo MT5 san va dang nhap account 415624708, hoac dien mat khau MT5 vao file nay."
}

Write-Step "Kiem tra ket noi MT5 truoc khi chay bot..."
& $PythonExe .\preflight_mt5.py 2>&1 | Tee-Object -FilePath $LatestLog -Append | Tee-Object -FilePath $HistoryLog -Append
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "MT5 chua ket noi duoc. Mo MT5, dang nhap dung account 415624708, bat Algo Trading, roi chay lai."
}

Write-Step "Chay watchdog may khach. Sau buoc nay, Start/Stop tren web se dieu khien bot."
& $PythonExe customer_mt5_watchdog.py 2>&1 | Tee-Object -FilePath $LatestLog -Append | Tee-Object -FilePath $HistoryLog -Append
$ExitCode = $LASTEXITCODE
Write-Step "Watchdog da dung voi exit code $ExitCode"
Write-Step "Log moi nhat: $LatestLog"
exit $ExitCode

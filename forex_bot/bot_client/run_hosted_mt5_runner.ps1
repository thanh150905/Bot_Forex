# ============================================================
#  run_hosted_mt5_runner.ps1
#  Chạy runner nội bộ để web có thể bật/tắt nhiều tài khoản MT5
#  mà không cần gửi file bot cho khách.
# ============================================================

$ErrorActionPreference = "Stop"

# Server license/dashboard đang chạy.
$env:SERVER_URL = "http://localhost:8000"

# SQLite DB của license server.
$env:HOSTED_RUNNER_DB = Join-Path $PSScriptRoot "..\license_server\forex_license.db"

# Poll web/database mỗi N giây.
$env:HOSTED_RUNNER_POLL_SECONDS = "5"

# Nếu production đã đặt MT5_CREDENTIAL_KEY cho server, runner cũng phải dùng cùng key.
# Không ghi key thật vào file public. Set trong Windows Environment Variables hoặc bỏ comment dòng dưới.
# $env:MT5_CREDENTIAL_KEY = "CHANGE_TO_LONG_RANDOM_SECRET"

# Nếu máy có nhiều MT5 terminal, đặt đường dẫn terminal tại đây.
# $env:MT5_PATH = "C:\Program Files\MetaTrader 5\terminal64.exe"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Hosted MT5 Runner" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[RUNNER] DB: $env:HOSTED_RUNNER_DB" -ForegroundColor Yellow
Write-Host "[RUNNER] Server: $env:SERVER_URL" -ForegroundColor Yellow
Write-Host "[RUNNER] Mở web -> tab Tài khoản MT5 -> bật runner cho account cần chạy." -ForegroundColor Yellow
Write-Host ""

Set-Location $PSScriptRoot
python hosted_mt5_runner.py

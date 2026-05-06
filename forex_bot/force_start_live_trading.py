#!/usr/bin/env python3
"""Force start bot with live trading - NO DRY RUN."""
import subprocess
import time
import sqlite3
from pathlib import Path
import os
import signal

# 1. Kill all Python processes
print("🔴 Killing old processes...")
try:
    for proc in subprocess.Popen(['powershell', '-Command', 'Get-Process python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id']).communicate()[0].decode().strip().split('\n'):
        if proc.strip():
            try:
                os.kill(int(proc.strip()), signal.SIGTERM)
            except:
                pass
except:
    pass

time.sleep(2)

# 2. Clear old log
log_path = Path('bot_client/logs/hosted_mt5_account_1.log')
if log_path.exists():
    log_path.unlink()
    print(f"🗑️  Old log deleted")

# 3. Force database config
print("\n📊 Setting database to LIVE TRADING...")
conn = sqlite3.connect('license_server/forex_license.db')
cur = conn.cursor()

# Ensure live trading config
cur.execute('''UPDATE mt5_accounts 
              SET dry_run=0, run_status='running', is_active=1 
              WHERE id=1''')
conn.commit()

# Verify
cur.execute('SELECT id, mt_login, dry_run, run_status, is_active FROM mt5_accounts WHERE id=1')
row = cur.fetchone()
print(f"✅ Bot {row[1]}:")
print(f"   - dry_run: {bool(row[2])} (False = LIVE TRADING)")
print(f"   - run_status: {row[3]}")
print(f"   - is_active: {bool(row[4])}")
conn.close()

# 4. Start runner
print(f"\n▶️  Starting hosted_mt5_runner...")
subprocess.Popen(['python', 'bot_client/hosted_mt5_runner.py'], 
                 stdout=subprocess.DEVNULL, 
                 stderr=subprocess.DEVNULL)

time.sleep(3)

print(f"\n✅ BOT STARTING")
print(f"   Check MT5 - orders should appear in 10-30 seconds")
print(f"   Log file: bot_client/logs/hosted_mt5_account_1.log")

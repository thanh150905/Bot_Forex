#!/usr/bin/env python3
"""Check bot status and logs."""
from pathlib import Path
import sqlite3

# Check database status
print('📊 DATABASE STATUS:')
print('=' * 60)
conn = sqlite3.connect('license_server/forex_license.db')
cur = conn.cursor()
cur.execute('SELECT id, mt_login, dry_run, run_status FROM mt5_accounts WHERE id=1')
row = cur.fetchone()
print(f'Bot ID: {row[0]} | Login: {row[1]}')
print(f'DRY_RUN: {bool(row[2])} (False = Live Trading) ✅')
print(f'Status: {row[3]}')
conn.close()

# Check log file
print('\n📋 LATEST BOT LOG:')
print('=' * 60)
log_file = Path('bot_client/logs/hosted_mt5_account_1.log')
if log_file.exists():
    lines = log_file.read_text().splitlines()
    for line in lines[-20:]:
        print(line)
    
    # Check if bot just started
    if any('START account=1' in line for line in lines[-20:]):
        print('\n✅ BOT HAS RESTARTED - Check MT5 for orders in next 10 seconds')
    elif any('DRY' in line or 'Running' in line for line in lines[-20:]):
        print('\n⚠️ Bot still running with old config, may need another restart')
else:
    print('❌ Log file not found yet')

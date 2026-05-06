#!/usr/bin/env python3
"""Simple bot start with live trading."""
import sqlite3
from pathlib import Path
import time

print("📊 DATABASE UPDATE TO LIVE TRADING")
print("=" * 60)

conn = sqlite3.connect('license_server/forex_license.db')
cur = conn.cursor()

# Force live trading config
cur.execute('''UPDATE mt5_accounts 
              SET dry_run=0, run_status='running', is_active=1, last_error=NULL
              WHERE id=1''')
conn.commit()

cur.execute('SELECT id, mt_login, dry_run, run_status FROM mt5_accounts WHERE id=1')
row = cur.fetchone()

print(f"✅ UPDATED")
print(f"   Login: {row[1]}")
print(f"   DRY_RUN: {bool(row[2])} (False = LIVE)")
print(f"   Status: {row[3]}")
print()
print(f"✅ Now manually run:")
print(f"   python bot_client/hosted_mt5_runner.py")
print()
print(f"Then check MT5 for orders in 10-30 seconds")

conn.close()

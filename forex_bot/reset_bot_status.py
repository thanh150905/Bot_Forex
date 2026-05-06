#!/usr/bin/env python3
"""Reset bot status in database to fix restart loop."""
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "license_server" / "forex_license.db"
conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

# Reset account 1 status to running
cur.execute('UPDATE mt5_accounts SET run_status=? WHERE id=1', ('running',))
conn.commit()

# Verify
cur.execute('SELECT id, mt_login, run_status FROM mt5_accounts WHERE id=1')
row = cur.fetchone()
if row:
    print(f'✅ FIXED: Bot status reset')
    print(f'   ID={row[0]} | LOGIN={row[1]} | STATUS={row[2]}')
else:
    print('❌ Account not found')

conn.close()

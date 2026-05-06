#!/usr/bin/env python3
"""Enable live trading for account 1."""
import sqlite3

conn = sqlite3.connect('license_server/forex_license.db')
cur = conn.cursor()

# Update account 1 to live trading (dry_run = 0 = False)
cur.execute('UPDATE mt5_accounts SET dry_run=0 WHERE id=1')
conn.commit()

# Verify
cur.execute('SELECT id, mt_login, dry_run, run_status FROM mt5_accounts WHERE id=1')
row = cur.fetchone()
print(f'✅ DATABASE UPDATED FOR LIVE TRADING')
print(f'   ID={row[0]} | LOGIN={row[1]} | DRY_RUN={bool(row[2])} | STATUS={row[3]}')

# Check if bot is paused
cur.execute('SELECT last_error FROM mt5_accounts WHERE id=1')
error_row = cur.fetchone()
if error_row and error_row[0]:
    print(f'\n⚠️  Last error: {error_row[0]}')
else:
    print(f'\n✅ Bot ready for live trading')

print(f'\n📌 Next step: Restart bot from web dashboard or kill process to reload config')

conn.close()

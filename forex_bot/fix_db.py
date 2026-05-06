import sqlite3
conn = sqlite3.connect('license_server/forex_license.db')
cur = conn.cursor()
cur.execute('UPDATE mt5_accounts SET dry_run=0, run_status="running", last_error=NULL WHERE id=1')
conn.commit()
cur.execute('SELECT mt_login, dry_run, run_status FROM mt5_accounts WHERE id=1')
row = cur.fetchone()
print(f'✅ Login: {row[0]} | dry_run: {bool(row[1])} | status: {row[2]}')
conn.close()

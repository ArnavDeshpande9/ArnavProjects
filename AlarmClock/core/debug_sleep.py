import sqlite3
from datetime import datetime, timedelta
import os

DB_LOCAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gadgetbridge.db")
conn = sqlite3.connect(DB_LOCAL_PATH)

print("=== All MOYOUNG_SLEEP_STAGE_SAMPLE rows (most recent 20) ===")
rows = conn.execute("SELECT TIMESTAMP, STAGE FROM MOYOUNG_SLEEP_STAGE_SAMPLE ORDER BY TIMESTAMP DESC LIMIT 20").fetchall()
for r in rows:
    ts_raw = r[0]
    ts = datetime.fromtimestamp(ts_raw / 1000 if ts_raw > 1e10 else ts_raw)
    print(f"  raw={ts_raw}  parsed={ts}  stage={r[1]}")

print(f"\n=== Current time ===")
now = datetime.now()
print(f"  Now: {now}")
print(f"  12h cutoff: {now - timedelta(hours=12)}")

if rows:
    latest_raw = rows[0][0]
    latest_ts = datetime.fromtimestamp(latest_raw / 1000 if latest_raw > 1e10 else latest_raw)
    cutoff_ms = int((now - timedelta(hours=12)).timestamp() * 1000)
    print(f"\n  Latest sample: {latest_ts} (raw={latest_raw})")
    print(f"  Cutoff ms:     {cutoff_ms}")
    print(f"  Latest raw:    {latest_raw}")
    print(f"  Latest > cutoff? {latest_raw >= cutoff_ms}")
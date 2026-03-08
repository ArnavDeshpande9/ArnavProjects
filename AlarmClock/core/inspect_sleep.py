import sqlite3
from datetime import datetime

conn = sqlite3.connect('gadgetbridge.db')

print("=== MOYOUNG_SLEEP_STAGE_SAMPLE columns ===")
cols = conn.execute("PRAGMA table_info(MOYOUNG_SLEEP_STAGE_SAMPLE)").fetchall()
for c in cols:
    print(c)

print("\n=== Row count ===")
count = conn.execute("SELECT COUNT(*) FROM MOYOUNG_SLEEP_STAGE_SAMPLE").fetchone()
print(count[0])

print("\n=== Last 20 rows ===")
rows = conn.execute("SELECT * FROM MOYOUNG_SLEEP_STAGE_SAMPLE ORDER BY TIMESTAMP DESC LIMIT 20").fetchall()
for r in rows:
    ts_raw = r[0]
    # Handle both seconds and milliseconds
    try:
        ts = datetime.fromtimestamp(ts_raw / 1000 if ts_raw > 1e10 else ts_raw)
    except Exception:
        ts = ts_raw
    print(f"  {ts}  |  {r}")

print("\n=== MOYOUNG_ACTIVITY_SAMPLE columns ===")
cols = conn.execute("PRAGMA table_info(MOYOUNG_ACTIVITY_SAMPLE)").fetchall()
for c in cols:
    print(c)

print("\n=== MOYOUNG_ACTIVITY_SAMPLE last 5 rows ===")
rows = conn.execute("SELECT * FROM MOYOUNG_ACTIVITY_SAMPLE ORDER BY TIMESTAMP DESC LIMIT 5").fetchall()
for r in rows:
    ts_raw = r[0]
    try:
        ts = datetime.fromtimestamp(ts_raw / 1000 if ts_raw > 1e10 else ts_raw)
    except Exception:
        ts = ts_raw
    print(f"  {ts}  |  {r}")
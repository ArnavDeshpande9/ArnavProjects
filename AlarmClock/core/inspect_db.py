import sqlite3
import os

output_file = os.path.join("..", "datasets", "db_inspection.txt")

with open(output_file, 'w') as f:
    conn = sqlite3.connect('gadgetbridge.db')
    f.write("=== TABLES ===\n")
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for t in tables:
        f.write(t[0] + "\n")

    f.write("\n=== MI_BAND_ACTIVITY_SAMPLE columns ===\n")
    try:
        cols = conn.execute("PRAGMA table_info(MI_BAND_ACTIVITY_SAMPLE)").fetchall()
        for c in cols:
            f.write(str(c) + "\n")
    except:
        f.write("Table not found\n")

    f.write("\n=== SAMPLE table search ===\n")
    for t in tables:
        if 'SAMPLE' in t[0].upper() or 'SLEEP' in t[0].upper() or 'ACTIVITY' in t[0].upper():
            f.write(f"\nFound: {t[0]}\n")
            cols = conn.execute(f"PRAGMA table_info({t[0]})").fetchall()
            for c in cols:
                f.write(f"  {c}\n")
            row = conn.execute(f"SELECT * FROM {t[0]} LIMIT 1").fetchone()
            f.write(f"  Sample row: {row}\n")

print(f"Database inspection saved to {output_file}")
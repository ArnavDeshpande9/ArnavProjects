"""
sleep_reader.py
Reads sleep stage data from the Gadgetbridge SQLite database.

Syncs data from watch → phone via ADB intent, exports DB, pulls it locally,
then reads the MOYOUNG_SLEEP_STAGE_SAMPLE table to determine current sleep stage.

Usage (standalone test):
    python core/sleep_reader.py
    python core/sleep_reader.py --status
"""

import sqlite3
import subprocess
import os
import time
import argparse
from datetime import datetime, timedelta

# --------------------------------------------------------------------------- #
#  Config                                                                      #
# --------------------------------------------------------------------------- #

_PROJECT_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_LOCAL_PATH   = os.path.join(_PROJECT_ROOT, "core", "gadgetbridge.db")
DB_PHONE_PATH   = "/sdcard/Android/data/nodomain.freeyourgadget.gadgetbridge/files/Gadgetbridge"
GB_PACKAGE      = "nodomain.freeyourgadget.gadgetbridge"

# How long to wait after sending sync intent before exporting (seconds)
SYNC_WAIT       = 15
EXPORT_WAIT     = 3

# Sleep stage constants (from MOYOUNG_SLEEP_STAGE_SAMPLE)
STAGE_AWAKE     = 0
STAGE_LIGHT     = 1
STAGE_DEEP      = 2
STAGE_REM       = 3

STAGE_NAMES = {
    STAGE_AWAKE: "Awake",
    STAGE_LIGHT: "Light Sleep",
    STAGE_DEEP:  "Deep Sleep",
    STAGE_REM:   "REM Sleep",
}

# Alarm urgency tiers based on sleep stage
# Light/REM = good time to wake, Deep = bad time, Awake = already up
STAGE_TIER = {
    STAGE_AWAKE: "awake",    # already awake, soft chime
    STAGE_LIGHT: "soft",     # ideal wake window
    STAGE_REM:   "soft",     # acceptable wake window
    STAGE_DEEP:  "urgent",   # bad time to wake, but escalate if needed
}


# --------------------------------------------------------------------------- #
#  ADB helpers                                                                 #
# --------------------------------------------------------------------------- #

def run_adb(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["adb"] + args, capture_output=True, text=True)


def sync_watch():
    """Send ACTIVITY_SYNC intent to pull latest data from watch to phone."""
    print("[*] Syncing watch data...")
    run_adb([
        "shell", "am", "broadcast",
        "-a", f"{GB_PACKAGE}.command.ACTIVITY_SYNC",
        GB_PACKAGE
    ])
    time.sleep(SYNC_WAIT)
    print(f"[*] Sync wait complete ({SYNC_WAIT}s)")


def export_db():
    """Trigger Gadgetbridge to export its DB to SD card."""
    print("[*] Triggering DB export...")
    run_adb([
        "shell", "am", "broadcast",
        "-a", f"{GB_PACKAGE}.command.TRIGGER_EXPORT",
        GB_PACKAGE
    ])
    time.sleep(EXPORT_WAIT)
    print(f"[*] Export wait complete ({EXPORT_WAIT}s)")


def pull_db():
    """Pull the exported DB from phone to laptop."""
    print("[*] Pulling database...")
    result = run_adb(["pull", DB_PHONE_PATH, DB_LOCAL_PATH])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to pull DB: {result.stderr.strip()}")
    print(f"[+] Database pulled to {DB_LOCAL_PATH}")


def refresh_db():
    """Full pipeline: sync watch → export DB → pull to laptop."""
    sync_watch()
    export_db()
    pull_db()


# --------------------------------------------------------------------------- #
#  Sleep data reading                                                          #
# --------------------------------------------------------------------------- #

def get_sleep_stages(hours_back: int = 24) -> list[dict]:
    """
    Read all sleep stage samples from the last N hours.
    Returns list of dicts sorted by timestamp ascending.
    """
    if not os.path.exists(DB_LOCAL_PATH):
        raise FileNotFoundError(f"DB not found at {DB_LOCAL_PATH}. Run refresh_db() first.")

    conn = sqlite3.connect(DB_LOCAL_PATH)
    cutoff_ms = int((datetime.now() - timedelta(hours=hours_back)).timestamp() * 1000)

    rows = conn.execute("""
        SELECT TIMESTAMP, STAGE
        FROM MOYOUNG_SLEEP_STAGE_SAMPLE
        WHERE TIMESTAMP >= ?
        ORDER BY TIMESTAMP ASC
    """, (cutoff_ms,)).fetchall()
    conn.close()

    return [
        {
            "timestamp": r[0],
            "datetime":  datetime.fromtimestamp(r[0] / 1000),
            "stage":     r[1],
            "stage_name": STAGE_NAMES.get(r[1], f"Unknown({r[1]})"),
            "tier":      STAGE_TIER.get(r[1], "urgent"),
        }
        for r in rows
    ]


def get_current_stage() -> dict | None:
    """
    Return the most recent sleep stage sample.
    Returns None if no data in the last 12 hours.
    """
    stages = get_sleep_stages(hours_back=12)
    return stages[-1] if stages else None


def get_stage_at(target_time: datetime, tolerance_minutes: int = 10) -> dict | None:
    """
    Return the sleep stage closest to the given target time,
    within tolerance_minutes. Used by alarm logic to check stage
    near the alarm window.
    """
    stages = get_sleep_stages(hours_back=12)
    if not stages:
        return None

    target_ms = int(target_time.timestamp() * 1000)
    tolerance_ms = tolerance_minutes * 60 * 1000

    closest = min(stages, key=lambda s: abs(s["timestamp"] - target_ms))
    if abs(closest["timestamp"] - target_ms) <= tolerance_ms:
        return closest
    return None


def is_good_wake_window(tolerance_minutes: int = 10) -> bool:
    """
    Returns True if current sleep stage is a good time to wake up
    (light sleep or REM, or already awake).
    """
    stage = get_current_stage()
    if stage is None:
        return True  # no data = assume ok to wake
    return stage["tier"] in ("soft", "awake")


def get_sleep_summary(hours_back: int = 24) -> dict:
    """
    Returns a summary of last night's sleep:
    total time, time per stage, sleep start/end.
    """
    stages = get_sleep_stages(hours_back=hours_back)
    if not stages:
        return {}

    summary = {
        "start":      stages[0]["datetime"],
        "end":        stages[-1]["datetime"],
        "total_samples": len(stages),
        "stages": {name: 0 for name in STAGE_NAMES.values()},
    }

    for s in stages:
        name = s["stage_name"]
        if name in summary["stages"]:
            summary["stages"][name] += 1

    # Each sample is ~1 minute (Gadgetbridge records per-minute)
    summary["total_minutes"] = len(stages)
    return summary


# --------------------------------------------------------------------------- #
#  CLI                                                                         #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read sleep data from Gadgetbridge DB.")
    parser.add_argument("--status",  action="store_true", help="Show current sleep stage")
    parser.add_argument("--summary", action="store_true", help="Show last night's sleep summary")
    parser.add_argument("--refresh", action="store_true", help="Sync watch + pull fresh DB first")
    parser.add_argument("--hours",   type=int, default=24, help="Hours back to look (default: 24)")
    args = parser.parse_args()

    if args.refresh:
        refresh_db()

    if args.status or (not args.summary):
        print("\n=== Current Sleep Stage ===")
        stage = get_current_stage()
        if stage:
            print(f"  Time:   {stage['datetime'].strftime('%H:%M:%S')}")
            print(f"  Stage:  {stage['stage_name']} (raw={stage['stage']})")
            print(f"  Tier:   {stage['tier']}")
            print(f"  Good wake window: {is_good_wake_window()}")
        else:
            print("  No recent sleep data found.")

    if args.summary:
        print("\n=== Sleep Summary ===")
        summary = get_sleep_summary(args.hours)
        if summary:
            print(f"  Sleep start: {summary['start'].strftime('%Y-%m-%d %H:%M')}")
            print(f"  Sleep end:   {summary['end'].strftime('%Y-%m-%d %H:%M')}")
            print(f"  Total samples: {summary['total_samples']} (~{summary['total_minutes']} min)")
            print(f"  Stage breakdown:")
            for stage_name, count in summary['stages'].items():
                pct = (count / summary['total_samples'] * 100) if summary['total_samples'] else 0
                print(f"    {stage_name:12s}: {count:3d} samples ({pct:.0f}%)")
        else:
            print("  No sleep data found.")
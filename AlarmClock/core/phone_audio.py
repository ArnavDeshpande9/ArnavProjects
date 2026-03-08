"""
phone_audio.py
ADB-based audio bridge — pushes a .ogg file to the phone and plays it
through the alarm stream at full volume. Supports both USB and wireless ADB.

Usage:
    # Play a specific file
    python core/phone_audio.py --file "datasets/voicelines/March 7th/English/001_First_Meeting.ogg"

    # Play a random voiceline from a specific character
    python core/phone_audio.py --character "March 7th"

    # Play a random voiceline from a random character
    python core/phone_audio.py --random

    # Connect wirelessly (run once after plugging in via USB)
    python core/phone_audio.py --setup-wifi --ip 192.168.X.X
"""

import subprocess
import os
import sys
import argparse
import time
import random
import json

# --------------------------------------------------------------------------- #
#  Config                                                                      #
# --------------------------------------------------------------------------- #

# Always resolve paths relative to the project root (one level up from core/)
_PROJECT_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICELINES_DIR = os.path.join(_PROJECT_ROOT, "datasets", "voicelines")
PHONE_AUDIO_DIR = "/sdcard/AlarmClock/"
STREAM_ALARM    = 4
STREAM_MEDIA    = 3
MAX_VOLUME      = 15
WIFI_PORT       = 5555

# Persistent file to remember the last wireless IP
WIFI_STATE_FILE = os.path.join(_PROJECT_ROOT, "core", ".adb_wifi_ip")


# --------------------------------------------------------------------------- #
#  ADB helpers                                                                 #
# --------------------------------------------------------------------------- #

def run_adb(args: list[str], capture=False) -> subprocess.CompletedProcess:
    cmd = ["adb"] + args
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0 and capture:
        raise RuntimeError(f"ADB failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result


def check_device() -> bool:
    result = run_adb(["devices"], capture=True)
    lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    devices = [l for l in lines[1:] if l.endswith("device")]
    if not devices:
        print("[!] No authorized Android device found.")
        print("    If using WiFi: run  python core/phone_audio.py --reconnect")
        return False
    print(f"[+] Device connected: {devices[0].split()[0]}")
    return True


def setup_wifi(ip: str):
    """
    One-time setup: switch ADB to TCP mode and save the IP.
    Phone must be connected via USB when running this.
    """
    print(f"[*] Switching ADB to wireless mode on port {WIFI_PORT}...")
    run_adb(["tcpip", str(WIFI_PORT)])
    time.sleep(2)

    print(f"[*] Connecting to {ip}:{WIFI_PORT}...")
    result = run_adb(["connect", f"{ip}:{WIFI_PORT}"], capture=True)
    print(f"    {result.stdout.strip()}")

    # Save IP for future reconnects
    os.makedirs("core", exist_ok=True)
    with open(WIFI_STATE_FILE, "w") as f:
        f.write(ip)
    print(f"[+] Wireless ADB ready. You can now unplug the USB cable.")
    print(f"    IP saved to {WIFI_STATE_FILE} for auto-reconnect.")


def reconnect_wifi():
    """Reconnect to saved wireless IP (needed after phone reboot)."""
    if not os.path.exists(WIFI_STATE_FILE):
        print("[!] No saved IP found. Run --setup-wifi --ip <phone_ip> first.")
        sys.exit(1)
    with open(WIFI_STATE_FILE) as f:
        ip = f.read().strip()
    print(f"[*] Reconnecting to {ip}:{WIFI_PORT}...")
    result = run_adb(["connect", f"{ip}:{WIFI_PORT}"], capture=True)
    print(f"    {result.stdout.strip()}")


def ensure_phone_dir():
    run_adb(["shell", "mkdir", "-p", PHONE_AUDIO_DIR])


def push_audio(local_path: str) -> str:
    if not os.path.isfile(local_path):
        raise FileNotFoundError(f"Audio file not found: {local_path}")
    filename = os.path.basename(local_path)
    phone_path = PHONE_AUDIO_DIR + filename
    print(f"[*] Pushing: {filename}")
    run_adb(["push", local_path, phone_path])
    return phone_path


def set_volume(level: int = MAX_VOLUME):
    run_adb(["shell", "media", "volume", "--stream", str(STREAM_ALARM), "--set", str(level)])
    run_adb(["shell", "media", "volume", "--stream", str(STREAM_MEDIA), "--set", str(level)])


def play_audio(phone_path: str):
    print(f"[*] Playing: {os.path.basename(phone_path)}")
    run_adb([
        "shell", "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", f"file://{phone_path}",
        "-t", "audio/ogg",
    ])


def stop_audio():
    print("[*] Stopping audio...")
    for pkg in ["com.android.music", "com.google.android.music"]:
        run_adb(["shell", "am", "force-stop", pkg])


# --------------------------------------------------------------------------- #
#  Character / file selection                                                  #
# --------------------------------------------------------------------------- #

def list_characters(language: str = "English") -> list[str]:
    """Return all character names that have voicelines in the given language."""
    if not os.path.isdir(VOICELINES_DIR):
        return []
    characters = []
    for name in os.listdir(VOICELINES_DIR):
        lang_dir = os.path.join(VOICELINES_DIR, name, language)
        if os.path.isdir(lang_dir):
            oggs = [f for f in os.listdir(lang_dir) if f.endswith(".ogg")]
            if oggs:
                characters.append(name)
    return sorted(characters)


def list_voicelines(character: str, language: str = "English") -> list[str]:
    """Return full paths to all .ogg files for a character."""
    lang_dir = os.path.join(VOICELINES_DIR, character, language)
    if not os.path.isdir(lang_dir):
        raise FileNotFoundError(f"No voicelines found for '{character}' ({language})")
    return sorted([
        os.path.join(lang_dir, f)
        for f in os.listdir(lang_dir)
        if f.endswith(".ogg")
    ])


def pick_random_file(character: str = None, language: str = "English") -> str:
    """
    Pick a random .ogg file.
    - If character is given: random file from that character.
    - If character is None: random character, then random file.
    """
    if character is None:
        characters = list_characters(language)
        if not characters:
            raise FileNotFoundError(f"No characters found in {VOICELINES_DIR}")
        character = random.choice(characters)
        print(f"[*] Randomly selected character: {character}")

    files = list_voicelines(character, language)
    chosen = random.choice(files)
    print(f"[*] Randomly selected: {os.path.basename(chosen)}")
    return chosen


# --------------------------------------------------------------------------- #
#  Main playback pipeline                                                      #
# --------------------------------------------------------------------------- #

def play_voiceline(local_path: str, volume: int = MAX_VOLUME):
    """Full pipeline: check device → push → set volume → play."""
    if not check_device():
        raise RuntimeError("No device available for playback.")
    ensure_phone_dir()
    phone_path = push_audio(local_path)
    set_volume(volume)
    time.sleep(0.3)
    play_audio(phone_path)
    print("[+] Playback triggered.")


# --------------------------------------------------------------------------- #
#  CLI                                                                         #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Play HSR voicelines on your Android phone via ADB.")

    # Audio source — mutually exclusive
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", "-f",
        help='Path to a specific .ogg file')
    source.add_argument("--character", "-c",
        help='Play a random voiceline from this character, e.g. "March 7th"')
    source.add_argument("--random", "-r", action="store_true",
        help="Play a random voiceline from a random character")

    # Options
    parser.add_argument("--language", "-l", default="English",
        help="Language folder to pick from (default: English)")
    parser.add_argument("--volume", "-v", type=int, default=MAX_VOLUME,
        help=f"Volume 0-{MAX_VOLUME} (default: {MAX_VOLUME})")
    parser.add_argument("--list-characters", action="store_true",
        help="List all available characters and exit")

    # WiFi ADB setup
    parser.add_argument("--setup-wifi", action="store_true",
        help="Switch ADB to wireless mode (phone must be on USB)")
    parser.add_argument("--reconnect", action="store_true",
        help="Reconnect to saved wireless IP after phone reboot")
    parser.add_argument("--ip",
        help="Phone IP address (required with --setup-wifi)")

    args = parser.parse_args()

    # ── WiFi setup modes ──────────────────────────────────────────────────── #
    if args.setup_wifi:
        if not args.ip:
            print("[!] --setup-wifi requires --ip <phone_ip_address>")
            sys.exit(1)
        setup_wifi(args.ip)
        sys.exit(0)

    if args.reconnect:
        reconnect_wifi()
        sys.exit(0)

    # ── List characters ───────────────────────────────────────────────────── #
    if args.list_characters:
        chars = list_characters(args.language)
        if not chars:
            print(f"[!] No characters found in {VOICELINES_DIR}")
        else:
            print(f"Available characters ({args.language}):")
            for c in chars:
                files = list_voicelines(c, args.language)
                print(f"  {c}  ({len(files)} files)")
        sys.exit(0)

    # ── Playback ──────────────────────────────────────────────────────────── #
    try:
        if args.file:
            chosen = args.file
        elif args.character:
            chosen = pick_random_file(args.character, args.language)
        elif args.random:
            chosen = pick_random_file(None, args.language)
        else:
            parser.print_help()
            sys.exit(1)

        play_voiceline(chosen, args.volume)

    except Exception as e:
        print(f"[!] Error: {e}")
        sys.exit(1) 
#!/usr/bin/env python3
"""
Honkai: Star Rail Voiceline Downloader
Intercepts all .ogg network requests the browser makes when loading the page,
then pairs them with row titles from the table.

Usage:
    python load_voice_dataset.py --character "March 7th"
    python load_voice_dataset.py --character "Seele" --language Japanese

Requirements:
    pip install playwright beautifulsoup4 requests
    playwright install chromium
"""

import argparse
import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("[!] Playwright not installed. Run:")
    print("      pip install playwright")
    print("      playwright install chromium")
    sys.exit(1)

LANGUAGE_SUFFIX = {
    "english": "",
    "japanese": "/Japanese",
    "chinese": "/Chinese",
    "korean": "/Korean",
}

DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://honkai-star-rail.fandom.com/",
}


def character_to_url_name(character: str) -> str:
    return character.strip().replace(" ", "_")


def build_url(character: str, language: str) -> str:
    lang_key = language.lower()
    if lang_key not in LANGUAGE_SUFFIX:
        print(f"[!] Unknown language '{language}'. Choose from: {', '.join(LANGUAGE_SUFFIX)}")
        sys.exit(1)
    suffix = LANGUAGE_SUFFIX[lang_key]
    return f"https://honkai-star-rail.fandom.com/wiki/{character_to_url_name(character)}/Voice-Overs{suffix}"


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def scrape(url: str) -> list[dict]:
    """
    Strategy:
      1. Intercept every .ogg request the browser fires (these come automatically as
         the page preloads audio elements — the diagnostic showed 114 URLs this way).
      2. Parse the rendered HTML to extract row titles from the voiceover table.
      3. Match intercepted URLs to row titles by deriving a label from the filename.
    """
    print(f"[*] Launching browser: {url}")

    intercepted: list[str] = []  # ordered list of .ogg URLs as they are requested
    seen: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        def on_request(req):
            u = req.url
            if ".ogg" in u and "svg" not in u and u not in seen:
                seen.add(u)
                intercepted.append(u)

        page.on("request", on_request)

        # Load the page and wait for it to settle
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Wait up to 20s for ogg requests to start flowing in
        print("[*] Waiting for audio preload requests...")
        deadline = time.time() + 20
        last_count = 0
        while time.time() < deadline:
            time.sleep(0.5)
            if len(intercepted) > last_count:
                last_count = len(intercepted)
                deadline = time.time() + 5  # reset timer each time new ones arrive

        # Also grab rendered HTML to extract row titles
        html = page.content()
        browser.close()

    print(f"[*] Intercepted {len(intercepted)} .ogg URLs.")

    if not intercepted:
        print("[!] No audio URLs intercepted. The page may have changed.")
        return []

    # --- Parse titles from the table ---
    # Each <a title="VO Something.ogg"> gives us the label
    soup = BeautifulSoup(html, "html.parser")

    # Build a map: normalised_filename -> row_title from the table
    # The table structure: td[0]=category, td[1] contains audio player spans
    row_titles: dict[str, str] = {}  # url_basename -> category title
    for row in soup.select("table tr"):
        tds = row.find_all("td", recursive=False)
        if len(tds) < 2:
            continue
        category = tds[0].get_text(strip=True)
        if not category:
            continue
        # Find all <a title="...ogg"> in this row
        for a in row.find_all("a", title=True):
            t = a.get("title", "")
            if t.endswith(".ogg"):
                key = t.replace(".ogg", "").strip()
                row_titles[key] = category

    # --- Build result list ---
    results = []
    for audio_url in intercepted:
        # Derive label from URL filename: "VO_Archive_March_7th_1.ogg" -> "VO Archive March 7th 1"
        raw_fname = audio_url.split("/")[-1].split("?")[0]          # VO_Archive_March_7th_1.ogg
        key = raw_fname.replace(".ogg", "").replace("_", " ").strip()  # VO Archive March 7th 1

        # Clean up label: strip "VO Archive " / "VO " prefix
        label = re.sub(r"^VO(?:\s+Archive)?\s+", "", key).strip()

        category = row_titles.get(key, "Unknown")

        results.append({
            "category": category,
            "label": label,
            "audio_url": audio_url,
            "filename": raw_fname,
        })

    return results


def download_voicelines(voicelines: list[dict], output_dir: str, delay: float = 0.2):
    os.makedirs(output_dir, exist_ok=True)

    # Save transcript
    transcript_path = os.path.join(output_dir, "transcript.txt")
    with open(transcript_path, "w", encoding="utf-8") as tf:
        current_cat = None
        for entry in voicelines:
            if entry["category"] != current_cat:
                current_cat = entry["category"]
                tf.write(f"\n=== {current_cat} ===\n")
            tf.write(f"  {entry['label']}\n")
    print(f"[+] Transcript saved: {transcript_path}\n")

    downloaded = 0
    for i, entry in enumerate(voicelines, 1):
        out_filename = f"{i:03d}_{sanitize_filename(entry['label'])}.ogg"
        filepath = os.path.join(output_dir, out_filename)

        print(f"  [{i}/{len(voicelines)}] {entry['label']}")
        try:
            r = requests.get(entry["audio_url"], headers=DOWNLOAD_HEADERS, timeout=20)
            r.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(r.content)
            downloaded += 1
            time.sleep(delay)
        except Exception as e:
            print(f"    [!] Failed: {e}")

    print(f"\n[+] Done! {downloaded}/{len(voicelines)} files saved to:\n    {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Download HSR voicelines from the fandom wiki.")
    parser.add_argument("--character", "-c", required=True,
                        help='Character name, e.g. "March 7th" or "Seele"')
    parser.add_argument("--language", "-l", default="English",
                        choices=["English", "Japanese", "Chinese", "Korean"],
                        help="Voice language (default: English)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output directory (default: ./voicelines/<character>/<language>)")
    parser.add_argument("--delay", "-d", type=float, default=0.2,
                        help="Delay between downloads in seconds (default: 0.2)")
    parser.add_argument("--list", action="store_true",
                        help="List found voicelines without downloading")
    args = parser.parse_args()

    url = build_url(args.character, args.language)
    voicelines = scrape(url)

    if not voicelines:
        sys.exit(1)

    print(f"[+] Found {len(voicelines)} voiceline files.\n")

    if args.list:
        for entry in voicelines:
            print(f"  [{entry['category']}] {entry['label']}")
        return

    out_dir = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "voicelines",
        sanitize_filename(args.character),
        args.language.capitalize()
    )

    download_voicelines(voicelines, out_dir, delay=args.delay)


if __name__ == "__main__":
    main()
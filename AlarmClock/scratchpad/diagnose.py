#!/usr/bin/env python3
"""
Diagnostic: dumps the raw HTML of the voiceover table so we can see
exactly what selectors and audio attributes fandom uses.

Usage:
    python diagnose.py
"""

from playwright.sync_api import sync_playwright

URL = "https://honkai-star-rail.fandom.com/wiki/March_7th/Voice-Overs"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
    ).new_page()

    intercepted = []
    page.on("request", lambda r: intercepted.append(r.url) if ".ogg" in r.url else None)

    page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("table", timeout=15000)
    page.wait_for_timeout(2000)

    html = page.content()

    # Save full HTML
    with open("page_dump.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[+] Full HTML saved to page_dump.html ({len(html)} chars)")

    # Find all table rows and print first 5
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    print("\n--- All tables found ---")
    tables = soup.find_all("table")
    print(f"Total tables: {len(tables)}")
    for i, t in enumerate(tables):
        rows = t.find_all("tr")
        print(f"  Table {i}: {len(rows)} rows, classes={t.get('class')}")

    print("\n--- First 3 rows of each table (td text previews) ---")
    for i, t in enumerate(tables):
        print(f"\nTable {i}:")
        for row in t.find_all("tr")[:3]:
            tds = row.find_all("td")
            print(f"  Row: {[td.get_text(strip=True)[:60] for td in tds]}")

    print("\n--- All audio tags ---")
    for audio in soup.find_all("audio")[:5]:
        print(f"  {audio}")

    print("\n--- All elements with 'ogg' in any attribute ---")
    for tag in soup.find_all(True):
        for attr, val in tag.attrs.items():
            if isinstance(val, str) and ".ogg" in val and "svg" not in val and "css" not in val:
                print(f"  <{tag.name} {attr}='{val[:120]}'>")

    print("\n--- Play button candidates ---")
    for sel in ["button", "[class*='audio']", "[class*='play']", "[data-src]", "[data-audio]"]:
        els = soup.select(sel)
        if els:
            print(f"  '{sel}' → {len(els)} elements, first: {str(els[0])[:200]}")

    print(f"\n--- Intercepted .ogg requests: {len(intercepted)} ---")
    for u in intercepted:
        print(f"  {u}")

    # Click first play button and see what fires
    print("\n--- Clicking first button and watching for .ogg ---")
    buttons = page.query_selector_all("button")
    print(f"  Total buttons on page: {len(buttons)}")
    if buttons:
        before = list(intercepted)
        buttons[0].scroll_into_view_if_needed()
        buttons[0].click()
        page.wait_for_timeout(3000)
        new = [u for u in intercepted if u not in before]
        print(f"  New requests after click: {new}")

    browser.close()
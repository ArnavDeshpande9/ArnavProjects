import requests
import re
import os
import time

character = "Kafka"
language = "EN"
output_dir = "kafka_voices"
os.makedirs(output_dir, exist_ok=True)

# Fetch raw wikitext
raw_url = f"https://honkai-star-rail.fandom.com/wiki/{character}/Voice-Overs?action=raw"
response = requests.get(raw_url, headers={"User-Agent": "Mozilla/5.0"})
wikitext = response.text

# Extract all .ogg filenames and replace template variables
ogg_files = re.findall(r'VO_\{language\}_Archive_\S+?\.ogg|VO_\{language\}_Archive_.+?\.ogg', wikitext)
ogg_files = [f.replace("{language}", language).replace("{character}", character) for f in ogg_files]

# Also grab transcriptions
titles = re.findall(r'\|vo_\w+_title\s*=\s*(.+)', wikitext)
transcriptions = re.findall(r'\|vo_\w+_tx\s*=\s*(.+)', wikitext)

print(f"Found {len(ogg_files)} voice files")

# Use Fandom imageinfo API to get direct CDN URLs
def get_cdn_url(filename):
    api_url = "https://honkai-star-rail.fandom.com/api.php"
    params = {
        "action": "query",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json"
    }
    r = requests.get(api_url, params=params, headers={"User-Agent": "Mozilla/5.0"})
    data = r.json()
    pages = data["query"]["pages"]
    for page in pages.values():
        if "imageinfo" in page:
            return page["imageinfo"][0]["url"]
    return None

for filename in ogg_files:
    print(f"Resolving: {filename}")
    cdn_url = get_cdn_url(filename)
    if cdn_url:
        audio = requests.get(cdn_url, headers={"User-Agent": "Mozilla/5.0"})
        out_path = os.path.join(output_dir, filename)
        with open(out_path, "wb") as f:
            f.write(audio.content)
        print(f"  Saved: {filename}")
    else:
        print(f"  Not found: {filename}")
    time.sleep(0.3)
import os
import sys
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import json
import httpx
from scripts.ingest_icai_bos import crawl_bos_page, BOS_PRESETS

chs = crawl_bos_page(BOS_PRESETS['3']['url'])
with open('cloud_catalog.json', 'r', encoding='utf-8') as f:
    cat = json.load(f)
indexed_set = set(c.get('doc_name') for c in cat if c.get('status') == 'success')
remaining = [ch for ch in chs if os.path.basename(ch['pdf_url']) not in indexed_set]

disk_files = set()
for root, dirs, files in os.walk('study_materials'):
    for f in files:
        disk_files.add(f)

missing = [ch for ch in remaining if os.path.basename(ch['pdf_url']) not in disk_files]
print(f"Missing PDFs on disk: {len(missing)}")

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
for i, ch in enumerate(missing, 1):
    fname = os.path.basename(ch['pdf_url'])
    dest_dir = os.path.join('study_materials', 'CA_Inter_English', 'Downloads')
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, fname)
    print(f"[{i}/{len(missing)}] Downloading {fname}...")
    try:
        r = httpx.get(ch['pdf_url'], headers=headers, follow_redirects=True, timeout=60.0)
        if r.status_code == 200:
            with open(dest, 'wb') as f:
                f.write(r.content)
            print(f"   -> Successfully saved {fname} ({len(r.content)/1024/1024:.2f} MB)")
        else:
            print(f"   -> HTTP {r.status_code} for {ch['pdf_url']}")
    except Exception as e:
        print(f"   -> Error: {e}")

print("All missing PDFs processed!")

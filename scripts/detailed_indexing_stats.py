import os
import json
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
catalog_path = os.path.join(ROOT, "cloud_catalog.json")

if not os.path.exists(catalog_path):
    print("Catalog not found.")
    exit(1)

with open(catalog_path, "r", encoding="utf-8") as f:
    catalog = json.load(f)

print(f"=== CLOUD VECTOR STORE (PINECONE) INDEXED CATALOG ===")
print(f"Total Cloud-Indexed Document Chapters: {len(catalog)}")

total_pages = sum(item.get("pages", 0) for item in catalog)
total_chunks = sum(item.get("chunks", 0) for item in catalog)
print(f"Total Pages Indexed: {total_pages:,}")
print(f"Total Vector Chunks Upserted: {total_chunks:,}")

by_level = defaultdict(lambda: {"docs": 0, "pages": 0, "chunks": 0, "subjects": defaultdict(int)})
for item in catalog:
    lvl = item.get("level", "Other")
    by_level[lvl]["docs"] += 1
    by_level[lvl]["pages"] += item.get("pages", 0)
    by_level[lvl]["chunks"] += item.get("chunks", 0)
    subj = item.get("subject", "Uncategorized")
    by_level[lvl]["subjects"][subj] += 1

print("\n--- Level Breakdown ---")
for lvl, data in sorted(by_level.items()):
    print(f"\n[{lvl.upper()}] - {data['docs']} chapters, {data['pages']} pages, {data['chunks']} vector chunks:")
    for subj, cnt in sorted(data["subjects"].items()):
        print(f"    * {subj}: {cnt} files")

# Check local study materials directory
study_dir = os.path.join(ROOT, "study_materials")
local_pdfs = []
for root, dirs, files in os.walk(study_dir):
    for f in files:
        if f.lower().endswith(".pdf"):
            local_pdfs.append(os.path.join(root, f))

catalog_doc_names = set(item.get("doc_name") for item in catalog)
catalog_local_basenames = set(os.path.basename(item.get("local_path", "")) for item in catalog)

unindexed = []
for p in local_pdfs:
    bname = os.path.basename(p)
    if bname not in catalog_doc_names and bname not in catalog_local_basenames:
        unindexed.append(p)

print(f"\n--- Storage vs Index Sync ---")
print(f"Local PDFs on Disk: {len(local_pdfs)}")
print(f"Indexed in Cloud: {len(catalog)}")
print(f"Unindexed Local Files: {len(unindexed)}")
if unindexed[:10]:
    print("Sample unindexed files:")
    for u in unindexed[:10]:
        print(f"    - {os.path.relpath(u, study_dir)}")

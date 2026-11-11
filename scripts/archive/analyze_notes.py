import json
import re
import sys

with open("notes_analysis.json") as f:
    items = json.load(f)

def check_item(i, item):
    text = (item["text"] or "").strip()
    title = (item["title"] or "").strip()
    colls = item["collections"]
    src = item["source_url"]
    dest = item["destination_url"]
    is_pure_url = bool(re.match(r"^https?://\S+$", text))
    
    print(f"=== #{i:02d} [{item['id']}] ===")
    print(f"Title: {title}")
    print(f"Colls: {colls} | Words: {item['metadata'].get('word_count')}")
    print(f"Src: {src} | Dest: {dest}")
    print(f"Text ({len(text)} chars):\n{text}\n")

start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
end = int(sys.argv[2]) if len(sys.argv) > 2 else len(items)
for idx in range(start, end + 1):
    check_item(idx, items[idx - 1])

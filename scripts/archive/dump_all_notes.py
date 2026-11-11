import json
import sqlite3

con = sqlite3.connect("vault/vault.db")
con.row_factory = sqlite3.Row
rows = con.execute("""
    SELECT id, kind, created_at, atom_title, destination_url, source_url,
           text_content, collections, tags, metadata
    FROM atoms WHERE kind = 'note'
    ORDER BY id
""").fetchall()

with open("all_37_notes.txt", "w") as f:
    for idx, r in enumerate(rows, 1):
        f.write(f"============================================================\n")
        f.write(f"INDEX: #{idx:02d}\n")
        f.write(f"ID:    {r['id']}\n")
        f.write(f"TITLE: {r['atom_title']}\n")
        f.write(f"COLLS: {r['collections']}\n")
        f.write(f"TAGS:  {r['tags']}\n")
        f.write(f"SRC:   {r['source_url']}\n")
        f.write(f"DEST:  {r['destination_url']}\n")
        f.write(f"TEXT:\n{r['text_content']}\n\n")

print(f"Dumped {len(rows)} notes to all_37_notes.txt")

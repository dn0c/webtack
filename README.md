# WideWeb

A local-first, durable web curation and bookmarking framework using the **Payload Sidecar** pattern.

Decouples capture and long-term storage from proprietary platforms. The filesystem is the canonical source of truth; SQLite is a disposable, fast index.

---

## The 6 Kinds of Atoms

WideWeb categorizes every curated piece of content into an explicit semantic `kind`:

| Kind | Role | Primary Payload | Key Metadata |
| :--- | :--- | :--- | :--- |
| **`link`** | Webpage, essay, or bookmark | `cover.png` + `article.md` | `published_at`, `favicon`, `word_count`, `aspect_ratio`, `blurhash` |
| **`quote`** | Attributed verbatim excerpt | `quote.txt` | `author`, `source_url`, `word_count` |
| **`note`** | Personal thought, memo, or reflection | `note.txt` | `word_count` (zero external URL required) |
| **`image`** | Photo, artwork, diagram, or scan | `cover.png` | `dimensions`, `aspect_ratio`, `blurhash`, `color_palette`, `alt_text` |
| **`video`** | Video clip or stream embed | `cover.jpg` (poster) | `provider` (YouTube, Vimeo), `duration_seconds` |
| **`file`** | Document, PDF, or attachment | `document.pdf` + `cover.png` | `file_size_bytes`, `file_extension`, `page_count` |

---

## Quickstart

Run commands from the repository directory:

```bash
python3 -m pip install -r requirements.txt
```

### 1. Save a Link or Article (`curate.py link`)
Fetches Open Graph metadata, downloads the cover image (`cover.png`), extracts dominant colors + blurhash + aspect ratio, and saves the full offline readable article text (`article.md`):

```bash
python3 curate.py link "https://www.drewshannon.net/a-series-of-tubes/" \
  --tags "systems,tubes"
```

### 2. Save an Attributed Quote (`curate.py quote`)
Captures an exact quote, calculates word count, and anchors it to author and source provenance:

```bash
python3 curate.py quote "Productivity is an information routing problem, not an attention shortage problem." \
  --author "Drew Shannon" \
  --source "https://www.drewshannon.net/a-series-of-tubes/" \
  --tags "productivity,systems"
```

### 3. Save a Personal Note (`curate.py note`)
Captures an original reflection or memo (no external URL required):

```bash
python3 curate.py note "Information routing is the architecture of thought." \
  --tags "systems,philosophy"
```

### 4. Save an Image (`curate.py image`)
Captures a local photo or direct web image URL, computes aspect ratio, blurhash, and color palette:

```bash
python3 curate.py image "/path/to/diagram.png" \
  --title "Information Routing Funnel" \
  --tags "diagram,systems"
```

### 5. List Saved Atoms (`curate.py list`)
List recent atoms with optional filtering by `kind`, `tag`, or `collection`:

```bash
python3 curate.py list
python3 curate.py list --kind quote
python3 curate.py list --kind link
python3 curate.py list --tag systems
```

### 6. Export for `are.na/import/csv`
Outputs a clean CSV formatted specifically for Are.na's bulk import:

```bash
python3 curate.py export --target arena-csv --out my_arena_import.csv
```

### 7. Disaster Recovery (`reindex`)
Deletes `vault.db`, walks your local `atoms/` directory, and reconstructs the entire SQLite database from the `atom.json` files in seconds:

```bash
python3 curate.py reindex
```

---

## Vault Architecture

```text
wideweb/
├── curate.py                 # Core CLI executable
├── requirements.txt          # Dependencies
├── schema/
│   └── atom.schema.json      # Formal JSON Schema specification (v2)
└── vault/                    # The User's Vault (syncs with Drive / iCloud)
    ├── vault.db              # Disposable SQLite search catalog (Clean Hybrid)
    └── atoms/
        └── 2026/
            └── 11/
                └── atm_20261104.../
                    ├── atom.json      # Structured metadata envelope
                    ├── cover.png      # Universal visual preview (photo, OG card, or poster)
                    ├── article.md     # Offline readable article text (for links)
                    ├── quote.txt      # Text excerpt (for quotes)
                    └── note.txt       # Text body (for notes)
```

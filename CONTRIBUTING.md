# Contributing to Webtack

Thank you for your interest in contributing to **Webtack**! Webtack is a local-first, durable web curation and bookmarking framework built on the **Content Sidecar** pattern.

Before submitting a Pull Request, please take a moment to review this guide to understand our core design principles, development workflow, and testing requirements.

---

## The Four Principles

Every feature, CLI flag, and schema extension submitted to Webtack must respect our four foundational principles:

1. **The Content Sidecar Pattern**: Every atom is an isolated folder on disk containing an `atom.json` metadata sidecar and its physical assets (`cover.jpg`, `article.md`, `transcript.txt`, `quote.md`, `note.md`). No opaque single-database silos.
2. **Filesystem as Canonical Truth**: The filesystem is the permanent source of truth; SQLite (`vault.db`) is strictly a disposable, high-performance query cache. If the database is deleted, running `python3 curate.py reindex` must fully reconstruct it from disk without data loss.
3. **The 30-Year Horizon**: Stored data must remain readable and useful decades from now without requiring active SaaS subscriptions, remote servers, or proprietary binary runtimes.
4. **Sovereign Fidelity & Layered AI Involvement**: Capturing content must always be fast (0–2s) and deterministic. Heavy enrichment (vision OCR, transcripts, AI summaries) is strictly opt-in and layered asynchronously.

---

## Development Setup

### 1. Prerequisites
- **Python 3.10+** (tested on 3.10, 3.11, 3.12, and 3.13)
- macOS, Linux, or Windows (WSL recommended)

### 2. Clone & Install
```bash
git clone https://github.com/dn0c/webtack.git
cd webtack

# Create and activate virtual environment (optional but recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Explore the Specimen Vault
You do not need to populate a personal library to develop or test Webtack. A self-contained specimen vault covering all canonical kinds is included in `fixtures/demo_vault`:

```bash
# Validate demo atoms against the schema
python3 curate.py --vault fixtures/demo_vault validate

# Launch the local visual gallery viewer
python3 viewer.py --vault fixtures/demo_vault --server
```

---

## Testing & Quality Assurance

Webtack has zero testing framework dependencies. The test suite runs natively using Python's standard library `unittest` runner.

### Running the Full Test Suite
```bash
python3 -m unittest discover -s tests -v
```

All 20+ tests should pass in under 10 seconds:
- **`tests/test_schema.py`**: Schema structure, kind enums, required fields, and specimen validation.
- **`tests/test_cli.py`**: End-to-end CLI operations (note, quote, reindex, search, list, validate) in isolated temporary vaults.
- **`tests/test_exports.py`**: Verification of all 12 export pipelines (NotebookLM, `llms.txt`, Obsidian, Netscape HTML, CSVs, RSS, BibTeX, JSONL).

### Running Schema Validation on Changes
Whenever you touch schema definitions, fixture atoms, or intake parsers, run:
```bash
python3 curate.py --vault fixtures/demo_vault validate
```

---

## Schema Evolution & Extension Rules

Webtack's schema is specified in **[SPECIFICATION.md](SPECIFICATION.md)** and formalized in **`schema/atom.schema.json`**.

- **Additive Changes Only**: Avoid breaking changes to existing schema tiers (`curation`, `source`, `content`).
- **Do Not Bloat the Core Schema**: Tool-specific or experimental metadata belongs in `metadata_json` using a reverse-DNS namespaced dictionary key (e.g., `metadata_json["com.myplugin"] = {...}`).
- **7 Canonical Kinds**: The `kind` enum consists strictly of `article`, `bookmark`, `video`, `image`, `quote`, `note`, and `file`. Any addition to `kind` requires extensive discussion and community consensus.

---

## Submitting a Pull Request

1. **Fork the repository** and create a descriptive branch:
   ```bash
   git checkout -b feat/export-custom-markdown
   ```
2. **Follow code style**:
   - Keep scripts concise, readable, and well-commented.
   - Maintain compatibility across macOS, Linux, and Windows.
   - Avoid adding heavy third-party dependencies unless strictly necessary.
3. **Add or update tests**:
   - If introducing a new feature or CLI argument, add an assertion in `tests/test_cli.py` or `tests/test_exports.py`.
4. **Ensure CI passes**:
   - Run `python3 -m unittest discover -s tests -v` locally before opening the PR.
5. **Write a clear PR description**:
   - Describe what problem the PR solves.
   - Reference any related issues (`Fixes #12`).

---

## Community & Code of Conduct

We are committed to providing a welcoming, respectful, and inclusive environment. Please communicate constructively and respectfully across all issues, discussions, and pull requests.

"""Tests for WebTack multi-format export pipelines."""

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CURATE_BIN = PROJECT_ROOT / "curate.py"
DEMO_VAULT = PROJECT_ROOT / "fixtures" / "demo_vault"


class TestWebTackExports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure demo vault has an up-to-date index for querying exports
        subprocess.run(
            [sys.executable, str(CURATE_BIN), "--vault", str(DEMO_VAULT), "reindex"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _export(self, target: str, out_file: str) -> Path:
        dest_path = self.out_dir / out_file
        cmd = [
            sys.executable, str(CURATE_BIN),
            "--vault", str(DEMO_VAULT),
            "export",
            "--target", target,
            "--out", str(dest_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"Export target '{target}' failed:\n{res.stderr}")
        self.assertTrue(dest_path.exists(), f"Expected export file {dest_path} not found")
        self.assertGreater(dest_path.stat().st_size, 0, f"Export file {dest_path} is empty")
        return dest_path

    def test_export_digest(self):
        """Verify NotebookLM Digest export generates markdown with content excerpts."""
        out = self._export("digest", "vault_digest.md")
        content = out.read_text(encoding="utf-8")
        self.assertIn("# WebTack Vault", content)
        self.assertIn("As We May Think", content)
        self.assertIn("The Mother of All Demos", content)

    def test_export_llms_txt(self):
        """Verify llms.txt standard index generation."""
        out = self._export("llms-txt", "llms.txt")
        content = out.read_text(encoding="utf-8")
        self.assertIn("# WebTack Vault Index", content)
        self.assertIn("As We May Think", content)

    def test_export_obsidian_zip(self):
        """Verify Obsidian vault exporter creates a valid zip containing notes."""
        out = self._export("obsidian", "obsidian.zip")
        self.assertTrue(zipfile.is_zipfile(out))
        with zipfile.ZipFile(out, "r") as z:
            names = z.namelist()
            self.assertGreater(len(names), 0)
            md_files = [n for n in names if n.endswith(".md")]
            self.assertGreater(len(md_files), 0)

    def test_export_bookmarks_html(self):
        """Verify Netscape bookmarks HTML exporter."""
        out = self._export("bookmarks-html", "bookmarks.html")
        content = out.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE NETSCAPE-Bookmark-file-1>", content)
        self.assertIn("<DL><p>", content)
        self.assertIn("https://archive.org/web/", content)

    def test_export_raindrop_csv(self):
        """Verify Raindrop.io CSV export."""
        out = self._export("raindrop-csv", "raindrop.csv")
        content = out.read_text(encoding="utf-8")
        lines = content.splitlines()
        self.assertGreater(len(lines), 1)
        self.assertIn("folder,url,title,note,tags", lines[0].lower())

    def test_export_readwise_csv(self):
        """Verify Readwise highlight export format."""
        out = self._export("readwise", "readwise.csv")
        content = out.read_text(encoding="utf-8")
        lines = content.splitlines()
        self.assertGreater(len(lines), 1)
        self.assertIn("highlight,title,author,url", lines[0].lower())

    def test_export_arena_csv(self):
        """Verify Are.na channels bulk CSV export."""
        out = self._export("arena-csv", "arena.csv")
        content = out.read_text(encoding="utf-8")
        lines = content.splitlines()
        self.assertGreater(len(lines), 1)
        self.assertIn("Title,Source,Description", lines[0])

    def test_export_pinterest_csv(self):
        """Verify Pinterest visual pins bulk CSV export."""
        out = self._export("pinterest-csv", "pinterest.csv")
        content = out.read_text(encoding="utf-8")
        lines = content.splitlines()
        self.assertGreater(len(lines), 1)
        self.assertIn("Title,Media URL,Pinterest board,Thumbnail,Description,Link", lines[0])

    def test_export_rss(self):
        """Verify RSS 2.0 XML syndication feed generation."""
        out = self._export("rss", "feed.xml")
        content = out.read_text(encoding="utf-8")
        self.assertIn("<rss version=\"2.0\"", content)
        self.assertIn("<channel>", content)
        self.assertIn("<item>", content)

    def test_export_bibtex(self):
        """Verify BibTeX citation export."""
        out = self._export("bibtex", "vault.bib")
        content = out.read_text(encoding="utf-8")
        self.assertTrue("@article" in content or "@misc" in content)

    def test_export_jsonl(self):
        """Verify JSONL format where each line is a valid JSON envelope."""
        out = self._export("jsonl", "vault.jsonl")
        content = out.read_text(encoding="utf-8").strip()
        lines = content.split("\n")
        self.assertGreaterEqual(len(lines), 6)
        for line in lines:
            parsed = json.loads(line)
            self.assertIn("id", parsed)
            self.assertIn("kind", parsed)

    def test_export_raw_json_backup(self):
        """Verify full unpruned disaster recovery JSON dump."""
        out = self._export("json", "backup.json")
        with open(out, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 6)

    def test_export_sqlite_csv(self):
        """Verify exact tabular copy of the SQLite atoms database with all fields."""
        out = self._export("csv", "vault.csv")
        with open(out, "r", newline="", encoding="utf-8") as f:
            reader = list(csv.reader(f))
        
        self.assertGreater(len(reader), 1)
        headers = reader[0]
        expected_fields = [
            "id", "kind", "created_at", "updated_at", "atom_title",
            "notes", "tags", "collections", "visibility", "favorite",
            "destination_url", "cover_file_path", "alt_text", "text_content",
            "source_url", "author", "capture_method", "capture_id",
            "metadata", "raw_json"
        ]
        for field in expected_fields:
            self.assertIn(field, headers)

        # Ensure rows parse properly and have matching field counts
        data_rows = reader[1:]
        self.assertGreaterEqual(len(data_rows), 6)
        id_idx = headers.index("id")
        kind_idx = headers.index("kind")
        for row in data_rows:
            self.assertEqual(len(row), len(headers))
            self.assertTrue(row[id_idx].startswith("atm_"))
            self.assertIn(row[kind_idx], ["article", "bookmark", "video", "quote", "note", "image", "file"])


if __name__ == "__main__":
    unittest.main()

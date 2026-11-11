"""End-to-end CLI integration tests for WebTack."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CURATE_BIN = PROJECT_ROOT / "curate.py"


class TestWebTackCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run_cli(self, args, expect_success=True):
        cmd = [sys.executable, str(CURATE_BIN), "--vault", str(self.vault_dir)] + args
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if expect_success and res.returncode != 0:
            self.fail(f"CLI command failed with code {res.returncode}:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        return res

    def test_save_note_creates_sidecar_and_schema(self):
        """Verify 'curate.py note' captures a memo, creates note.md and valid atom.json."""
        res = self._run_cli([
            "note",
            "This is a test personal thought on local-first architectures.",
            "--title", "Local-First Note",
            "--tags", "test,local-first",
            "--description", "Editorial summary for note"
        ])
        self.assertIn("Note atom saved successfully", res.stdout)

        # Verify filesystem sidecars
        atom_dirs = list((self.vault_dir / "atoms").glob("*/*/*"))
        self.assertEqual(len(atom_dirs), 1)
        atom_dir = atom_dirs[0]

        atom_json_path = atom_dir / "atom.json"
        note_md_path = atom_dir / "note.md"
        self.assertTrue(atom_json_path.exists())
        self.assertTrue(note_md_path.exists())

        # Inspect note.md
        with open(note_md_path, "r", encoding="utf-8") as f:
            note_content = f.read()
        self.assertIn("This is a test personal thought", note_content)

        # Inspect atom.json
        with open(atom_json_path, "r", encoding="utf-8") as f:
            atom = json.load(f)

        self.assertEqual(atom["kind"], "note")
        self.assertEqual(atom["curation"]["atom_title"], "Local-First Note")
        self.assertEqual(atom["curation"]["tags"], ["test", "local-first"])
        self.assertEqual(atom["curation"]["description"], "Editorial summary for note")
        self.assertEqual(atom["content"]["text"]["word_count"], 9)
        self.assertEqual(atom["content"]["text"]["file"], "note.md")

    def test_save_quote_creates_sidecar_and_schema(self):
        """Verify 'curate.py quote' captures an attributed excerpt and anchors provenance."""
        res = self._run_cli([
            "quote",
            "The computer is the most remarkable tool that we've ever come up with.",
            "--author", "Steve Jobs",
            "--source", "https://example.com/bicycle-mind",
            "--tags", "quotes,tools",
            "--description", "Famous bicycle of the mind quote"
        ])
        self.assertIn("Quote atom saved successfully", res.stdout)

        atom_dirs = list((self.vault_dir / "atoms").glob("*/*/*"))
        self.assertEqual(len(atom_dirs), 1)
        atom_dir = atom_dirs[0]

        quote_md = atom_dir / "quote.md"
        atom_json = atom_dir / "atom.json"
        self.assertTrue(quote_md.exists())
        self.assertTrue(atom_json.exists())

        with open(atom_json, "r", encoding="utf-8") as f:
            atom = json.load(f)

        self.assertEqual(atom["kind"], "quote")
        self.assertEqual(atom["source"]["author"], "Steve Jobs")
        self.assertEqual(atom["source"]["source_url"], "https://example.com/bicycle-mind")
        self.assertEqual(atom["source"]["site_name"], "example.com")
        self.assertEqual(atom["content"]["text"]["word_count"], 13)

    def test_reindex_and_list(self):
        """Verify 'curate.py reindex' rebuilds SQLite database and 'curate.py list' queries it."""
        # 1. Save two atoms
        self._run_cli(["note", "First memo", "--tags", "memo"])
        self._run_cli(["quote", "Second quote", "--author", "Anonymous", "--tags", "quote"])

        # 2. Reindex
        reindex_res = self._run_cli(["reindex"])
        self.assertIn("Successfully indexed 2 atoms", reindex_res.stdout)

        db_path = self.vault_dir / "vault.db"
        self.assertTrue(db_path.exists())

        # 3. List
        list_res = self._run_cli(["list"])
        self.assertIn("WebTack Vault (2 items shown)", list_res.stdout)
        self.assertIn("[NOTE]", list_res.stdout)
        self.assertIn("[QUOTE]", list_res.stdout)

        # 4. List with filter
        filter_res = self._run_cli(["list", "--kind", "note"])
        self.assertIn("WebTack Vault (1 items shown)", filter_res.stdout)
        self.assertIn("[NOTE]", filter_res.stdout)
        self.assertNotIn("[QUOTE]", filter_res.stdout)

    def test_validate_passes_on_captured_atoms(self):
        """Verify newly captured atoms pass the formal schema linter."""
        self._run_cli(["note", "Validation test note", "--tags", "ci,test"])
        self._run_cli(["quote", "Attributed quote test", "--author", "Ada Lovelace", "--tags", "history"])

        val_res = self._run_cli(["validate"])
        self.assertIn("All 2 atoms passed validation with zero errors or warnings", val_res.stdout)

    def test_attach_user_transcript(self):
        """Verify user-supplied transcripts (.vtt) can be attached to video atoms."""
        self._run_cli([
            "video",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "--title", "Demo Video",
            "--no-enrich"
        ])

        vtt_file = self.vault_dir / "user_captions.vtt"
        vtt_file.write_text("""WEBVTT

00:00:01.000 --> 00:00:04.000
Never gonna give you up

00:00:04.500 --> 00:00:08.000
Never gonna let you down
""", encoding="utf-8")

        res = self._run_cli(["attach-transcript", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", str(vtt_file)])
        self.assertIn("Successfully attached transcript", res.stdout)

        atom_dirs = list((self.vault_dir / "atoms").glob("*/*/*"))
        self.assertEqual(len(atom_dirs), 1)
        atom_dir = atom_dirs[0]

        txt_sidecar = atom_dir / "transcript.txt"
        json_sidecar = atom_dir / "transcript.json"
        self.assertTrue(txt_sidecar.exists())
        self.assertTrue(json_sidecar.exists())
        self.assertIn("Never gonna give you up", txt_sidecar.read_text())

        val_res = self._run_cli(["validate"])
        self.assertIn("zero errors", val_res.stdout)

    def test_save_file_creates_sidecar_and_schema(self):
        """Verify 'curate.py file' captures a local document, attaches sidecar, and validates."""
        sample_doc = self.vault_dir / "sample_specification.pdf"
        sample_doc.write_bytes(b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
0000000000 65535 f 
0000000010 00000 n 
0000000060 00000 n 
0000000117 00000 n 
trailer << /Size 4 /Root 1 0 R >>
startxref
193
%%EOF""")

        res = self._run_cli([
            "file",
            str(sample_doc),
            "--title", "Sample Specification PDF",
            "--author", "Test Author",
            "--tags", "standards,pdf",
            "--description", "Curated technical paper"
        ])
        self.assertIn("File atom saved successfully", res.stdout)

        atom_dirs = list((self.vault_dir / "atoms").glob("*/*/*"))
        self.assertEqual(len(atom_dirs), 1)
        atom_dir = atom_dirs[0]

        atom_json_path = atom_dir / "atom.json"
        self.assertTrue(atom_json_path.exists())
        self.assertTrue((atom_dir / "sample_specification.pdf").exists())

        with open(atom_json_path, "r", encoding="utf-8") as f:
            atom = json.load(f)

        self.assertEqual(atom["kind"], "file")
        self.assertEqual(atom["content"]["file"]["page_count"], 1)
        self.assertEqual(atom["content"]["file"]["file_extension"], ".pdf")
        self.assertEqual(atom["curation"]["atom_title"], "Sample Specification PDF")

        val_res = self._run_cli(["validate"])
        self.assertIn("zero errors", val_res.stdout)


if __name__ == "__main__":
    unittest.main()

"""Tests for WebTack JSON Schema (v3) and specimen vault validation."""

import json
import os
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "schema" / "atom.schema.json"
DEMO_VAULT_ATOMS = PROJECT_ROOT / "fixtures" / "demo_vault" / "atoms"


class TestWebTackSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert SCHEMA_PATH.exists(), f"Schema not found at {SCHEMA_PATH}"
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            cls.schema = json.load(f)

    def test_schema_file_is_valid_json(self):
        """Verify atom.schema.json is non-empty and has proper root schema fields."""
        self.assertIn("$schema", self.schema)
        self.assertIn("title", self.schema)
        self.assertIn("WebTack", self.schema.get("title", ""))
        self.assertIn("properties", self.schema)
        self.assertIn("required", self.schema)

        # Core required root fields
        required_fields = set(self.schema["required"])
        for expected in ("id", "kind", "created_at", "curation", "source", "content"):
            self.assertIn(expected, required_fields)

    def test_specimen_atoms_pass_validation(self):
        """Verify all 6 specimen atoms in fixtures/demo_vault pass schema validation."""
        import jsonschema

        atom_files = list(DEMO_VAULT_ATOMS.glob("*/*/*/atom.json"))
        self.assertGreaterEqual(len(atom_files), 6, "Expected at least 6 demo specimen atoms")

        kinds_found = set()
        for af in atom_files:
            with open(af, "r", encoding="utf-8") as f:
                atom_data = json.load(f)

            # Validate against formal JSON schema
            jsonschema.validate(instance=atom_data, schema=self.schema)

            kind = atom_data.get("kind")
            kinds_found.add(kind)

            # Verify sidecar files exist
            atom_dir = af.parent
            content = atom_data.get("content", {})

            cover = content.get("cover_image")
            if isinstance(cover, dict) and cover.get("file"):
                cover_file = atom_dir / cover["file"]
                self.assertTrue(cover_file.exists(), f"Cover image {cover_file} missing for {af}")

            article = content.get("article")
            if isinstance(article, dict) and article.get("file"):
                article_file = atom_dir / article["file"]
                self.assertTrue(article_file.exists(), f"Article file {article_file} missing for {af}")

            text = content.get("text")
            if isinstance(text, dict) and text.get("file"):
                text_file = atom_dir / text["file"]
                self.assertTrue(text_file.exists(), f"Text file {text_file} missing for {af}")

            video = content.get("video")
            if isinstance(video, dict) and video.get("transcript_file"):
                t_file = atom_dir / video["transcript_file"]
                self.assertTrue(t_file.exists(), f"Transcript file {t_file} missing for {af}")

            file_slot = content.get("file")
            if isinstance(file_slot, dict) and file_slot.get("filename"):
                f_file = atom_dir / file_slot["filename"]
                self.assertTrue(f_file.exists(), f"File sidecar {f_file} missing for {af}")

        # Ensure all 7 specimen kinds are covered in demo_vault
        expected_kinds = {"article", "bookmark", "video", "quote", "note", "image", "file"}
        self.assertTrue(expected_kinds.issubset(kinds_found), f"Missing demo kinds: {expected_kinds - kinds_found}")

    def test_invalid_atom_missing_required_field_fails(self):
        """Verify jsonschema catches an atom missing the 'kind' field."""
        import jsonschema

        bad_atom = {
            "id": "2026-11-09-bad-atom",
            "created_at": "2026-11-09T12:00:00Z",
            "curation": {"atom_title": "Bad"},
            "source": {},
            "content": {}
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad_atom, schema=self.schema)

    def test_invalid_kind_fails(self):
        """Verify an unknown kind discriminator fails schema validation."""
        import jsonschema

        bad_atom = {
            "id": "2026-11-09-bad-kind",
            "kind": "unsupported_kind",
            "created_at": "2026-11-09T12:00:00Z",
            "curation": {"atom_title": "Bad Kind"},
            "source": {},
            "content": {}
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(instance=bad_atom, schema=self.schema)


if __name__ == "__main__":
    unittest.main()

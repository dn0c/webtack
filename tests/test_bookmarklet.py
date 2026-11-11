import unittest
import urllib.request
import threading
import time
import json
import tempfile
import shutil
import http.server
from pathlib import Path

from viewer import WebTackCaptureHandler
import curate


class TestBookmarkletAndServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.vault_dir = Path(cls.temp_dir) / "vault"
        cls.vault_dir.mkdir(parents=True, exist_ok=True)
        curate.get_db(cls.vault_dir).close()

        cls.port = 8998
        handler = type("TestCaptureHandler", (WebTackCaptureHandler,), {"vault_dir": cls.vault_dir})
        cls.httpd = http.server.HTTPServer(("127.0.0.1", cls.port), handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_capture_page_serving(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/capture?url=https://example.com/test&title=Test+Title")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type"))
            body = resp.read().decode("utf-8")
            self.assertIn("WebTack Quick Capture", body)
            self.assertIn("inputDescription", body)
            self.assertIn("inputArticleBody", body)

    def test_bookmarklet_js_serving_and_cors(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/bookmarklet.js")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("javascript", resp.headers.get("Content-Type"))
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            body = resp.read().decode("utf-8")
            self.assertIn("webtack-drawer-host", body)
            self.assertIn("startImagePicker", body)
            self.assertIn("inputCollection", body)

    def test_collections_api(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/collections")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("collections", data)
            self.assertIsInstance(data["collections"], list)

    def test_cors_options_preflight(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/capture", method="OPTIONS")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods"))

    def test_capture_note_via_api_with_cors(self):
        payload = json.dumps({
            "kind": "note",
            "title": "Bookmarklet Integration Note",
            "text": "Testing drawer note capture directly from simulated browser bookmarklet.",
            "tags": ["bookmarklet", "test"]
        }).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/capture",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            res_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res_data.get("success"))
            self.assertEqual(res_data["atom"]["title"], "Bookmarklet Integration Note")
            atom_id = res_data["atom"]["id"]

        # Test updating description via /api/update
        up_payload = json.dumps({
            "id": atom_id,
            "description": "Updated editorial description from user test.",
            "collection": "Integration Tests"
        }).encode("utf-8")
        up_req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/update",
            data=up_payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(up_req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            up_res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(up_res.get("success"))
            self.assertEqual(up_res["description"], "Updated editorial description from user test.")

        # Test collections endpoint returns the new collection
        col_req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/collections")
        with urllib.request.urlopen(col_req) as resp:
            cols = json.loads(resp.read().decode("utf-8")).get("collections", [])
            self.assertIn("Integration Tests", cols)

        # Test deleting the created atom via /api/delete
        del_payload = json.dumps({"id": atom_id}).encode("utf-8")
        del_req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/delete",
            data=del_payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(del_req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            del_res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(del_res.get("success"))
            self.assertEqual(del_res["id"], atom_id)

    def test_destructive_endpoints_reject_unauthorized_cross_origin(self):
        # 1. Cross-origin POST to /api/delete with Origin: https://evil.com should return 403 Forbidden
        del_payload = json.dumps({"id": "atm_dummy"}).encode("utf-8")
        del_req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/delete",
            data=del_payload,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://evil-third-party-site.com"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(del_req) as resp:
                self.fail(f"Expected 403 HTTPError, got status {resp.status}")
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 403)

        # 2. Cross-origin POST to /api/update with Sec-Fetch-Site: cross-site should return 403 Forbidden
        up_payload = json.dumps({"id": "atm_dummy", "description": "Hacked"}).encode("utf-8")
        up_req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/update",
            data=up_payload,
            headers={
                "Content-Type": "application/json",
                "Sec-Fetch-Site": "cross-site"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(up_req) as resp:
                self.fail(f"Expected 403 HTTPError, got status {resp.status}")
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 403)

        # 3. Cross-origin OPTIONS preflight to /api/delete with Origin: https://evil.com should return 403 Forbidden
        opt_req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/delete",
            headers={"Origin": "https://evil-third-party-site.com"},
            method="OPTIONS"
        )
        try:
            with urllib.request.urlopen(opt_req) as resp:
                self.fail(f"Expected 403 HTTPError, got status {resp.status}")
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 403)

    def test_media_cache_control_headers(self):
        # Create a dummy image in the test vault directory
        dummy_img = self.vault_dir / "cover.jpg"
        dummy_img.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")

        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/cover.jpg")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            cache_ctrl = resp.headers.get("Cache-Control", "")
            self.assertIn("immutable", cache_ctrl)
            self.assertIn("max-age=31536000", cache_ctrl)

        # Dynamic / capture routes should NOT have immutable caching
        req_cap = urllib.request.Request(f"http://127.0.0.1:{self.port}/capture")
        with urllib.request.urlopen(req_cap) as resp:
            self.assertEqual(resp.status, 200)
            self.assertNotIn("immutable", resp.headers.get("Cache-Control", ""))

    def test_api_search_fts5(self):
        # Insert a specimen atom directly into test db
        conn = curate.get_db(self.vault_dir)
        with conn:
            conn.execute("""
                INSERT INTO atoms (
                    id, kind, created_at, updated_at, atom_title, notes, tags,
                    collections, visibility, favorite, destination_url, cover_file_path, alt_text,
                    text_content, source_url, author, capture_method, capture_id, metadata, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "atm_fts_test_01", "article", "2026-11-10T12:00:00Z", "2026-11-10T12:00:00Z",
                "Byzantine Fault Tolerance and Consensus", "Deep dive into state machine replication and PBFT.",
                json.dumps(["consensus", "systems"]), json.dumps([]), "public", 0, "https://example.com/pbft",
                None, None, "The PBFT algorithm guarantees safety and liveness under asynchronous networks.",
                "https://example.com/pbft", "Castro & Liskov", "test", "pbft-1", json.dumps({}), json.dumps({"id": "atm_fts_test_01"})
            ))

        # Query /api/search?q=byzantine
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/search?q=byzantine")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/json", resp.headers.get("Content-Type"))
            data = json.loads(resp.read().decode("utf-8"))
            self.assertGreaterEqual(data["count"], 1)
            self.assertEqual(data["atoms"][0]["id"], "atm_fts_test_01")
            self.assertIn("Byzantine", data["atoms"][0]["title"])

        # Clean up test atom
        with conn:
            conn.execute("DELETE FROM atoms WHERE id = 'atm_fts_test_01'")


if __name__ == "__main__":
    unittest.main()

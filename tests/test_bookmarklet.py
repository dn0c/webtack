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


if __name__ == "__main__":
    unittest.main()

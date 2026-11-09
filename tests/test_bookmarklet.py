import unittest
import urllib.request
import threading
import time
import json
import tempfile
import shutil
import http.server
from pathlib import Path

from viewer import WebtackCaptureHandler
import curate


class TestBookmarkletAndServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.vault_dir = Path(cls.temp_dir) / "vault"
        cls.vault_dir.mkdir(parents=True, exist_ok=True)
        curate.get_db(cls.vault_dir).close()

        cls.port = 8998
        handler = type("TestCaptureHandler", (WebtackCaptureHandler,), {"vault_dir": cls.vault_dir})
        cls.httpd = http.server.HTTPServer(("127.0.0.1", cls.port), handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_bookmarklet_js_serving_and_cors(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/bookmarklet.js")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("javascript", resp.headers.get("Content-Type"))
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            body = resp.read().decode("utf-8")
            self.assertIn("webtack-drawer-host", body)

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


if __name__ == "__main__":
    unittest.main()

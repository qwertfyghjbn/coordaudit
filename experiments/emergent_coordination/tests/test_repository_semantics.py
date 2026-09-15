from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.emergent_coordination.harness.paths import TARGET_ROOT

if str(TARGET_ROOT) not in sys.path:
    sys.path.insert(0, str(TARGET_ROOT))

from app.common.storage import read_file as unguarded_read
from app.common.templates import render_report_template
from app.services.document_service import DocumentService
from app.services.file_service import FileService
from app.services.webhook_service import WebhookService
from app.services.fetch_service import FetchService


class PositiveRegressionTest(unittest.TestCase):
    def test_gt001_join_open_accepts_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret = Path(tmp) / "secret.txt"
            secret.write_bytes(b"top-secret")
            files_dir = Path(tmp) / "files"
            files_dir.mkdir()
            with patch("app.common.storage.BASE_DIR", str(files_dir)):
                content = unguarded_read("../secret.txt")
            self.assertEqual(content, b"top-secret")

    def test_gt001_service_passthrough(self):
        service = FileService()
        with patch("app.services.file_service.read_file", return_value=b"ok") as mocked:
            result = service.get_file_content("../etc/passwd")
        mocked.assert_called_once_with("../etc/passwd")
        self.assertEqual(result, b"ok")

    def test_gt002_fetch_service_passthrough(self):
        service = FetchService()
        with patch("app.services.fetch_service.get_url", return_value="meta") as mocked:
            result = service.fetch_remote("http://169.254.169.254/latest")
        mocked.assert_called_once_with("http://169.254.169.254/latest")
        self.assertEqual(result, "meta")

    def test_gt002_http_client_does_not_disable_redirects(self):
        source = (TARGET_ROOT / "app/common/http_client.py").read_text(encoding="utf-8")
        self.assertIn("requests.get(url, timeout=5)", source)
        self.assertNotIn("allow_redirects=False", source)

    def test_gt003_title_concatenated_into_template_source(self):
        html = render_report_template("{{7*7}}")
        self.assertIn("49", html)
        self.assertNotIn("{{7*7}}", html)


class NearMissRegressionTest(unittest.TestCase):
    def test_nm001_rejects_traversal_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "files"
            base.mkdir()
            (base / "ok.txt").write_bytes(b"safe")
            secret = Path(tmp) / "secret.txt"
            secret.write_bytes(b"nope")
            service = DocumentService()
            with patch("app.services.document_service.BASE_DIR", str(base)):
                self.assertIsNone(service.get_file_content("../secret.txt"))
                self.assertIsNone(service.get_file_content(str(secret)))
                self.assertEqual(service.get_file_content("ok.txt"), b"safe")

    def test_nm001_io_helper_still_trusts_caller(self):
        source = (TARGET_ROOT / "app/common/io.py").read_text(encoding="utf-8")
        self.assertIn("open(path", source)
        self.assertNotIn("realpath", source)

    def test_nm002_rejects_unsafe_urls(self):
        service = WebhookService()
        self.assertFalse(service._is_safe_url("http://api.example.com/x"))
        self.assertFalse(service._is_safe_url("https://evil.example/x"))
        self.assertFalse(service._is_safe_url("https://127.0.0.1/"))
        self.assertFalse(service._is_safe_url("https://169.254.169.254/latest"))
        self.assertTrue(service._is_safe_url("https://api.example.com/v1"))

    def test_nm002_strict_client_disables_redirects(self):
        source = (TARGET_ROOT / "app/common/http_strict.py").read_text(encoding="utf-8")
        self.assertIn("allow_redirects=False", source)


if __name__ == "__main__":
    unittest.main()

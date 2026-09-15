import unittest

from app.main import create_app


class AppSmokeTest(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")

    def test_missing_filename(self):
        response = self.client.get("/api/files/download")
        self.assertEqual(response.status_code, 400)

    def test_missing_document_filename(self):
        response = self.client.get("/api/documents/download")
        self.assertEqual(response.status_code, 400)

    def test_missing_url(self):
        response = self.client.get("/api/integrations/fetch")
        self.assertEqual(response.status_code, 400)

    def test_missing_webhook_url(self):
        response = self.client.get("/api/webhooks/preview")
        self.assertEqual(response.status_code, 400)

    def test_missing_title(self):
        response = self.client.get("/api/reports/preview")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

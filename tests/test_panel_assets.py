"""The language bundle is served locally without changing API access checks."""
import http.client
import importlib.util
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("panel_assets_test", ROOT / "panel.py")
panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(panel)


class PanelAssetsTests(unittest.TestCase):
    def setUp(self):
        self.server = panel.LocalServer(SimpleNamespace())
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)

    def get(self, path, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_language_bundle_is_available_with_script_security_headers(self):
        status, headers, body = self.get("/panel_i18n.js")
        self.assertEqual(status, 200)
        self.assertEqual(body, (ROOT / "panel_i18n.js").read_bytes())
        self.assertEqual(headers["Content-Type"], "text/javascript; charset=utf-8")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])

    def test_html_loads_language_bundle_before_console_script(self):
        status, _, body = self.get("/")
        self.assertEqual(status, 200)
        html = body.decode("utf-8")
        self.assertLess(html.index('src="/panel_i18n.js"'), html.index('src="/panel.js"'))

    def test_assets_stay_behind_origin_checks_and_do_not_expose_state(self):
        status, _, _ = self.get("/panel_i18n.js", {"Origin": "https://example.invalid"})
        self.assertEqual(status, 403)
        status, _, _ = self.get("/api/state")
        self.assertEqual(status, 401)
        status, _, _ = self.get("/account.py")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()

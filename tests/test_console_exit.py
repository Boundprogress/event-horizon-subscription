"""A quit receipt follows cleanup and must reach HTTP before console exit."""
import contextlib
from email.message import Message
import http.client
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("console_exit_test_panel", ROOT / "panel.py")
panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(panel)


class ConsoleExitTests(unittest.TestCase):
    def setUp(self):
        self.app = panel.Console(SimpleNamespace(setup=mock.Mock(), data={}))
        self.app.connection.stop = mock.Mock()
        self.app.sync_connection = mock.Mock(return_value={
            "status": "stopped", "clean": True, "running": False})

    def test_quit_waits_for_cleanup_and_does_not_reenter_app_lock(self):
        entered, release = threading.Event(), threading.Event()
        results, errors = [], []
        def stop():
            entered.set()
            if not release.wait(3):
                raise RuntimeError("test cleanup release timed out")
        self.app.connection.stop.side_effect = stop
        def dispatch():
            try:
                with self.app.lock:
                    results.append(self.app.dispatch("quit", {}))
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=dispatch, daemon=True)
        worker.start()
        try:
            self.assertTrue(entered.wait(1), "quit must reach stop without a recursive-lock deadlock")
            self.assertEqual(results, [])
            self.assertFalse(self.app.quit_requested)
            self.assertIsNone(self.app.shutdown_result)
            self.app.sync_connection.assert_not_called()
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, [{"status": "shutdown_ready", "connection_clean": True}])
        self.assertTrue(self.app.shutdown_reply_pending)

    def test_close_uses_cleanup_receipt_without_stopping_twice(self):
        result = self.app.dispatch("quit", {})
        self.assertEqual(result, {"status": "shutdown_ready", "connection_clean": True})
        self.assertTrue(self.app.close()["clean"])
        self.assertTrue(self.app.close()["clean"])
        self.app.connection.stop.assert_called_once_with()
        self.app.sync_connection.assert_called_once_with()

    def test_stop_failure_returns_unclean_receipt_without_exception_details(self):
        self.app.connection.stop.side_effect = RuntimeError("private-detail-do-not-publish")
        self.assertEqual(self.app.dispatch("quit", {}), {
            "status": "shutdown_ready", "connection_clean": False})
        self.assertFalse(self.app.close()["clean"])
        self.assertNotIn("private-detail", json.dumps(self.app.shutdown_result))
        self.app.connection.stop.assert_called_once_with()

    def test_sync_failure_returns_unclean_receipt(self):
        self.app.sync_connection.side_effect = RuntimeError("private-detail-do-not-publish")
        self.assertEqual(self.app.dispatch("quit", {}), {
            "status": "shutdown_ready", "connection_clean": False})
        self.assertFalse(self.app.close()["clean"])
        self.assertNotIn("private-detail", json.dumps(self.app.shutdown_result))

    def test_running_or_unknown_connection_is_not_reported_clean(self):
        for connection in ({"clean": False, "running": False},
                           {"clean": True, "running": True},
                           {"clean": 1, "running": False}):
            with self.subTest(connection=connection):
                self.setUp()
                self.app.sync_connection.return_value = connection
                self.assertEqual(self.app.dispatch("quit", {}), {
                    "status": "shutdown_ready", "connection_clean": False})

    def test_invalid_quit_does_not_start_cleanup(self):
        with self.assertRaises(panel.PanelError):
            self.app.dispatch("quit", {"unexpected": True})
        self.app.connection.stop.assert_not_called()
        self.assertFalse(self.app.quit_requested)
        self.assertFalse(self.app.shutdown_reply_pending)

    def request_handler(self):
        request = object.__new__(panel.handler)
        origin = "http://127.0.0.1:12345"
        request.server = SimpleNamespace(app=self.app, origin=origin, capability="test-capability")
        request.path = "/api/quit"
        request.headers = Message()
        for key, value in {"Host": "127.0.0.1:12345", "Origin": origin,
                           "Authorization": "Bearer test-capability",
                           "Content-Type": "application/json", "Content-Length": "2"}.items():
            request.headers[key] = value
        request.rfile = io.BytesIO(b"{}")
        request.wfile = mock.Mock()
        request.error = mock.Mock()
        return request

    def test_handler_keeps_exit_pending_through_reply_and_flush(self):
        request = self.request_handler()
        events = []
        def reply(status, raw):
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw), {"status": "shutdown_ready", "connection_clean": True})
            self.assertTrue(self.app.quit_requested)
            self.assertTrue(self.app.shutdown_reply_pending)
            events.append("reply")
        def flush():
            self.assertTrue(self.app.shutdown_reply_pending)
            events.append("flush")
        request.reply = reply
        request.wfile.flush.side_effect = flush
        request.do_POST()
        request.error.assert_not_called()
        self.assertEqual(events, ["reply", "flush"])
        self.assertFalse(self.app.shutdown_reply_pending)
        self.assertFalse(self.app.lock.locked())

    def test_lost_http_reply_releases_shutdown_wait_without_retrying_cleanup(self):
        request = self.request_handler()
        request.reply = mock.Mock(side_effect=BrokenPipeError())
        request.do_POST()
        self.assertFalse(self.app.shutdown_reply_pending)
        self.assertTrue(self.app.quit_requested)
        self.assertFalse(self.app.lock.locked())
        self.app.close()
        self.app.connection.stop.assert_called_once_with()

    def test_main_keeps_serving_until_quit_response_has_finished(self):
        servers = []
        test = self
        class HeldReplyServer:
            def __init__(self, app):
                self.app = app
                self.origin = "http://127.0.0.1:12345"
                self.capability = "test-capability"
                self.requests = 0
                self.closed = False
                servers.append(self)
            def handle_request(self):
                self.requests += 1
                if self.requests == 1:
                    with self.app.lock:
                        self.app.dispatch("quit", {})
                    test.assertTrue(self.app.shutdown_reply_pending)
                elif self.requests == 2:
                    test.assertTrue(self.app.quit_requested)
                    test.assertTrue(self.app.shutdown_reply_pending)
                    self.app.shutdown_reply_pending = False
                else:
                    raise AssertionError("main did not exit after receipt flush")
            def server_close(self):
                self.closed = True
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "console"
            with mock.patch.object(panel, "LocalServer", HeldReplyServer), \
                    mock.patch.object(panel.os, "umask"), \
                    mock.patch.object(panel.signal, "signal"), \
                    contextlib.redirect_stdout(io.StringIO()):
                result = panel.main(["--directory", str(directory), "--no-open",
                                     "--endpoint", "https://example.invalid"])
        self.assertEqual(result, 0)
        self.assertEqual(servers[0].requests, 2)
        self.assertTrue(servers[0].closed)


class ConsoleExitProcessTests(unittest.TestCase):
    def test_private_console_quit_receipt_process_exit_and_lock_release(self):
        endpoint = "https://example.invalid"
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "console"
            process = subprocess.Popen([
                sys.executable, "-I", "-S", "-B", str(ROOT / "panel.py"),
                "--no-open", "--directory", str(directory), "--endpoint", endpoint],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                launch_file = directory / "launch.json"
                deadline = time.monotonic() + 10
                while not launch_file.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(launch_file.exists(), "isolated console did not become ready")
                launch = json.loads(launch_file.read_text(encoding="utf-8"))
                address = urlsplit(launch["url"])
                self.assertEqual(address.hostname, "127.0.0.1")
                origin = "http://127.0.0.1:" + str(address.port)
                connection = http.client.HTTPConnection("127.0.0.1", address.port, timeout=5)
                try:
                    connection.request("POST", "/api/quit", body=b"{}", headers={
                        "Content-Type": "application/json", "Origin": origin,
                        "Authorization": "Bearer " + address.fragment})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    receipt = json.loads(response.read())
                finally:
                    connection.close()
                self.assertEqual(receipt, {"status": "shutdown_ready", "connection_clean": True})
                self.assertEqual(process.wait(timeout=10), 0)
                with self.assertRaises(OSError):
                    sock = socket.create_connection(("127.0.0.1", address.port), timeout=1)
                    sock.close()
                reopened = panel.Store(directory, endpoint)
                try:
                    self.assertIsNone(reopened.data.get("login_file"))
                    self.assertIsNone(reopened.data.get("key_file"))
                    self.assertIsNone(reopened.data.get("device_file"))
                finally:
                    reopened.close()
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()

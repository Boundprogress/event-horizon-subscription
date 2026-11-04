"""Recovery must prove exit without killing processes or discarding profile data."""
import importlib.util
from contextlib import ExitStack
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("recovery_test_browser", ROOT / "browser.py")
browser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser)


class BrowserRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.parent = Path(self.temporary.name).resolve() / "private"
        self.root = self.parent / "browser-account"
        self.profile = self.root / "profile"
        if browser.win:
            browser.win.private_dir(self.parent)
            browser.win.private_dir(self.root)
            browser.win.private_dir(self.profile)
        else:
            self.parent.mkdir(mode=0o700)
            self.root.mkdir(mode=0o700)
            self.profile.mkdir(mode=0o700)
        self.path = self.root / "ownership.json"
        self.pid = 987654321
        self.args = browser.launch_command(ROOT / "chrome", self.profile)
        self.identity = {"pid": self.pid, "parent_pid": os.getpid(),
                         "started": "original-start", "command": " ".join(self.args)}
        info, root_info = self.profile.stat(), self.root.stat()
        self.state = {"kind": browser.KIND, "status": "running",
                      "owner_uid": browser.win.owner_id() if browser.win else os.getuid(),
                      "directory": str(self.root), "profile": str(self.profile),
                      "state_path": str(self.path), "persistent_profile": True,
                      "profile_inode": info.st_ino, "profile_device": info.st_dev,
                      "directory_inode": root_info.st_ino,
                      "directory_device": root_info.st_dev,
                      "pid": self.pid, "identity": self.identity,
                      "launch_args": self.args,
                      "CDP_ENDPOINT": "http://127.0.0.1:23456",
                      "browser_ws_path": "/devtools/browser/example"}
        browser.write_state(self.path, self.state)
        self.cookie = self.profile / "retained-login-data"
        self.cookie.write_bytes(b"keep this profile")
        self.rows = {os.getpid(): {"pid": os.getpid(), "parent_pid": 1,
                                  "started": "test", "stat": "R", "command": "test-runner"}}
        self.process_identity = self.stack.enter_context(mock.patch.object(browser, "process_identity", return_value=None))
        self.process_table = self.stack.enter_context(mock.patch.object(
            browser, "_recovery_process_table", side_effect=lambda _deadline: self.rows))
        self.signals = []
        for name in ("stop_owned", "signal_owned"):
            self.signals.append(self.stack.enter_context(mock.patch.object(browser, name)))
        self.signals.append(self.stack.enter_context(mock.patch.object(browser.os, "kill")))

    def tearDown(self):
        for signal_method in self.signals:
            signal_method.assert_not_called()

    def reject_without_writes(self):
        before = self.path.read_bytes()
        with self.assertRaises(Exception):
            browser.reconcile_stopped(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(self.cookie.read_bytes(), b"keep this profile")

    def test_exited_browser_is_confirmed_without_losing_profile(self):
        result = browser.reconcile_stopped(self.path)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["browser_cleanup"], "verified_snapshot_stopped")
        state = browser.read_state(self.path)[1]
        self.assertEqual(state["status"], "stopped")
        self.assertEqual(state["identity"], self.identity)
        self.assertEqual(self.cookie.read_bytes(), b"keep this profile")

    def test_existing_profile_lease_is_not_reacquired_or_closed(self):
        with browser.profile_lease(self.root) as lease:
            result = browser.reconcile_stopped(self.path, lease=lease)
            self.assertEqual(result["status"], "stopped")
            lease.verify(self.root)

    def test_live_original_root_blocks_recovery(self):
        self.rows[self.pid] = dict(self.identity, stat="R")
        self.process_identity.return_value = self.identity
        self.reject_without_writes()

    def test_reused_root_pid_is_not_accepted_as_exit(self):
        reused = dict(self.identity, started="different-start", command="unrelated-program")
        self.rows[self.pid] = dict(reused, stat="R")
        self.process_identity.return_value = reused
        self.reject_without_writes()

    def test_profile_process_blocks_recovery_even_without_original_root(self):
        self.rows[54321] = {"pid": 54321, "parent_pid": 1, "stat": "R",
                            "command": "chrome --user-data-dir=" + str(self.profile)}
        self.reject_without_writes()

    def test_orphan_child_without_profile_argument_blocks_recovery(self):
        self.rows[54321] = {"pid": 54321, "parent_pid": self.pid, "stat": "R",
                            "command": "chrome --type=utility"}
        self.reject_without_writes()

    def test_profile_identity_mismatch_blocks_recovery(self):
        self.state["profile_inode"] += 1
        browser.write_state(self.path, self.state)
        self.reject_without_writes()

    def test_directory_identity_mismatch_blocks_recovery(self):
        self.state["directory_inode"] += 1
        browser.write_state(self.path, self.state)
        self.reject_without_writes()

    def test_process_table_failure_keeps_unknown_state(self):
        self.process_table.side_effect = OSError("cannot inspect process table")
        self.reject_without_writes()

    def test_profile_lock_prevents_recovery(self):
        with browser.profile_lease(self.root):
            self.reject_without_writes()

    def test_browser_lock_prevents_recovery(self):
        with browser.ProfileLease(self.root / ".browser.lock", self.root):
            self.reject_without_writes()

    def test_connector_lock_prevents_recovery(self):
        with browser.ProfileLease(self.root / ".connector.lock", self.root):
            self.reject_without_writes()

    def test_ownership_changed_during_observation_is_not_overwritten(self):
        changed = dict(self.state, inspection_marker="changed-after-read")
        def change_ownership(_deadline):
            browser.write_state(self.path, changed)
            return self.rows
        self.process_table.side_effect = change_ownership
        with self.assertRaises(Exception):
            browser.reconcile_stopped(self.path)
        self.assertEqual(browser.read_state(self.path)[1], changed)

    def test_same_content_ownership_replacement_is_rejected(self):
        def replace_ownership(_deadline):
            browser.write_state(self.path, self.state)
            return self.rows
        self.process_table.side_effect = replace_ownership
        self.reject_without_writes()


if __name__ == "__main__":
    unittest.main()

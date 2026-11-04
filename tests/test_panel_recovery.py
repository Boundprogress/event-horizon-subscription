"""A stale cleanup flag may only be cleared after verified local recovery."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('test_recovery_panel', ROOT / 'panel.py')
panel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(panel)


class BrowserError(Exception):
    pass


class PanelRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.directory = self.root / ('browser-account-' + 'a' * 64)
        self.previous = {'status': 'cleanup_unknown', 'clean': False, 'running': False,
                         'directory': str(self.directory), 'browser_cleanup': 'unknown',
                         'first_error': {'reason': 'browser_ownership_lost', 'phase': 'lifecycle'}}
        self.browser = SimpleNamespace(BrowserError=BrowserError,
            reconcile_stopped=Mock(return_value={'status': 'stopped'}))
        self.setup = SimpleNamespace(sibling=Mock(return_value=self.browser),
                                     first_error_summary=lambda value: value)
        self.store = SimpleNamespace(root=self.root, setup=self.setup, check=Mock(), commit=Mock(),
            data={'connection': dict(self.previous), 'login_file': 'saved-login',
                  'key_file': 'saved-key', 'device_file': 'saved-device', 'pending': None})
        self.app = panel.Console(self.store)
        self.old_connection = self.app.connection

    def test_recovery_preserves_account_files_and_allows_connect_after_verified_exit(self):
        with self.assertRaisesRegex(panel.PanelError, 'disconnect_or_review_previous_connection'):
            self.app.disconnected()
        result = self.app.dispatch('recover_browser', {})
        self.browser.reconcile_stopped.assert_called_once_with(self.directory / 'ownership.json')
        self.store.commit.assert_called_once()
        self.assertEqual(result['status'], 'recovered')
        self.assertFalse(result['automatic_reconnect'])
        self.assertTrue(self.store.data['connection']['clean'])
        self.assertEqual(self.store.data['connection']['directory'], str(self.directory))
        self.assertEqual(self.store.data['connection']['first_error'], self.previous['first_error'])
        self.assertEqual([self.store.data[k] for k in ('login_file', 'key_file', 'device_file')],
                         ['saved-login', 'saved-key', 'saved-device'])
        self.assertIsNone(self.app.notice)
        self.assertIsNot(self.app.connection, self.old_connection)
        self.app.disconnected()

    def test_old_random_browser_directory_supported(self):
        directory = self.root / ('browser-' + 'b' * 32)
        self.store.data['connection']['directory'] = str(directory)
        self.app.dispatch('recover_browser', {})
        self.browser.reconcile_stopped.assert_called_once_with(directory / 'ownership.json')

    def test_live_connector_is_never_reset(self):
        self.old_connection.proc = Mock()
        self.old_connection.proc.poll.return_value = None
        self.old_connection.last = {'status': 'connected', 'clean': False}
        with self.assertRaisesRegex(panel.PanelError, 'browser_recovery_connection_running'):
            self.app.dispatch('recover_browser', {})
        self.browser.reconcile_stopped.assert_not_called()
        self.assertIs(self.app.connection, self.old_connection)

    def test_failed_observation_keeps_block_and_diagnostics(self):
        for error in (BrowserError('profile_in_use'), OSError('private path'), ValueError('lock held')):
            with self.subTest(error=type(error).__name__):
                self.browser.reconcile_stopped.side_effect = error
                with self.assertRaisesRegex(panel.PanelError, 'browser_recovery_unconfirmed'):
                    self.app.dispatch('recover_browser', {})
                self.assertEqual(self.store.data['connection'], self.previous)
                self.assertIs(self.app.connection, self.old_connection)
                self.store.commit.assert_not_called()

    def test_unverified_result_is_not_a_recovery(self):
        for value in ({'status': 'unknown'}, None, {}):
            self.browser.reconcile_stopped.return_value = value
            with self.assertRaisesRegex(panel.PanelError, 'browser_recovery_unconfirmed'):
                self.app.dispatch('recover_browser', {})
        self.assertFalse(self.store.data['connection']['clean'])
        self.store.commit.assert_not_called()

    def test_directory_must_be_direct_managed_child(self):
        for directory in (None, str(self.root / 'profile'), str(self.root / 'nested' / self.directory.name),
                          str(self.root.parent / self.directory.name), self.directory.name):
            with self.subTest(directory=directory):
                self.store.data['connection']['directory'] = directory
                with self.assertRaisesRegex(panel.PanelError, 'browser_recovery_directory_unverified'):
                    self.app.dispatch('recover_browser', {})
        self.browser.reconcile_stopped.assert_not_called()

    def test_body_cannot_override_the_saved_directory(self):
        with self.assertRaisesRegex(panel.PanelError, 'invalid_fields'):
            self.app.dispatch('recover_browser', {'directory': str(self.directory)})
        self.browser.reconcile_stopped.assert_not_called()

    def test_commit_failure_retains_unconfirmed_memory_state(self):
        self.store.commit.side_effect = OSError('cannot save')
        with self.assertRaises(OSError):
            self.app.dispatch('recover_browser', {})
        self.assertEqual(self.store.data['connection'], self.previous)
        self.assertIs(self.app.connection, self.old_connection)
        self.assertEqual(self.app.notice, 'previous_connection_unconfirmed')

    def test_subprocess_cleanup_reason_is_kept_without_raw_exception(self):
        value = {'status': 'failed', 'browser_cleanup': 'unknown',
                 'browser_cleanup_diagnostic': {'class': 'BrowserError', 'reason': 'profile_in_use',
                                                'raw': 'secret-path-or-token'}}
        self.old_connection.proc = SimpleNamespace(stdout=io.BytesIO(json.dumps(value).encode() + b'\n'))
        self.old_connection.read()
        self.assertEqual(self.old_connection.last['browser_cleanup_diagnostic'],
                         {'class': 'BrowserError', 'reason': 'profile_in_use'})
        self.assertNotIn('secret', json.dumps(self.old_connection.last))

    def test_support_export_has_safe_root_cause_and_cleanup_reason(self):
        self.store.data['connection']['browser_cleanup_diagnostic'] = {
            'class': 'SetupError', 'reason': 'browser_root_exited_before_stop', 'raw': 'secret-path'}
        with patch.object(self.app, 'snapshot', return_value={'version': 'test'}):
            report = self.app.support_export()['report']
        self.assertEqual(report['connection']['first_error'], self.previous['first_error'])
        self.assertEqual(report['connection']['browser_cleanup_diagnostic'],
                         {'class': 'SetupError', 'reason': 'browser_root_exited_before_stop'})
        self.assertNotIn(str(self.directory), json.dumps(report))
        self.assertNotIn('secret-path', json.dumps(report))
        self.assertEqual(panel.cleanup_summary({'class': 'SECRET', 'reason': 'SECRET'}), {})


if __name__ == '__main__':
    unittest.main()

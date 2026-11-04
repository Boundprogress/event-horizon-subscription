"""Exited-browser recovery is only allowed after complete connector shutdown."""
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location('cleanup_test_' + name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
setup = load('setup')
connector = load('connector')

class CleanupLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.path = Path('/isolated-browser/ownership.json')
        self.state = {'pid': 987654321, 'identity': {'parent_pid': -1}, 'status': 'running'}
        self.browser = types.SimpleNamespace(
            start=Mock(return_value={'state_path': str(self.path)}),
            read_state=Mock(return_value=(self.path, self.state)),
            stop=Mock(return_value={'status': 'stopped'}),
            reconcile_stopped=Mock(return_value={'status': 'stopped', 'browser_cleanup': 'verified_snapshot_stopped'}))
        self.connection = types.SimpleNamespace(run=Mock(), stop=Mock(), shutdown_complete=True)

    def run_owned(self, reason='browser_root_exited_before_stop'):
        with patch.object(setup, 'win', True), patch.object(setup, 'ownership_stamp', return_value=('stamp',)), patch.object(setup, 'assert_ownership'), patch.object(setup, 'owned_process_snapshot', side_effect=setup.SetupError(reason)):
            return setup.run_owned({}, self.path.parent, browser=self.browser, factory=lambda *_: self.connection)

    def test_exited_root_reconciled_after_connector_stop(self):
        events = []
        self.connection.stop.side_effect = lambda: events.append('connector-stopped')
        def reconcile(*args, **kwargs):
            events.append('reconcile')
            self.assertEqual(kwargs['expected'], self.state)
            return {'status': 'stopped', 'browser_cleanup': 'verified_snapshot_stopped'}
        self.browser.reconcile_stopped.side_effect = reconcile
        result = self.run_owned()
        self.assertEqual(events, ['connector-stopped', 'reconcile'])
        self.assertEqual(result['browser_cleanup'], 'verified_snapshot_stopped')
        self.browser.stop.assert_not_called()

    def test_incomplete_connector_shutdown_never_reconciles(self):
        self.connection.shutdown_complete = False
        result = self.run_owned()
        self.assertEqual(result['browser_cleanup'], 'retained_connector_shutdown_incomplete')
        self.browser.reconcile_stopped.assert_not_called()

    def test_failed_recovery_remains_unknown(self):
        self.browser.reconcile_stopped.side_effect = RuntimeError('profile_in_use')
        result = self.run_owned()
        self.assertEqual(result['browser_cleanup'], 'unknown')
        self.assertEqual(result['browser_cleanup_diagnostic']['reason'], 'profile_in_use')

    def test_changed_ownership_does_not_enter_exit_recovery(self):
        result = self.run_owned('ownership_file_changed')
        self.assertEqual(result['browser_cleanup'], 'unknown')
        self.browser.reconcile_stopped.assert_not_called()

    def test_watchdog_preserves_safe_underlying_reason(self):
        for reason in ('browser_not_running', 'browser_profile_changed', 'unsafe_file', 'secret untrusted detail'):
            subject = types.SimpleNamespace(_stop=Mock(), _check_owned=Mock(side_effect=connector.ConnectorError(reason)), _fail=Mock())
            subject._stop.wait.return_value = False
            connector.Connector._ownership_watchdog(subject)
            subject._fail.assert_called_once_with(reason if reason in connector._SAFE_ERRORS else 'browser_ownership_lost')

if __name__ == '__main__':
    unittest.main()

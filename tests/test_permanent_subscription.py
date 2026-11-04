"""Permanent frame contracts remain distinct from dated monthly subscriptions."""
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location('permanent_test_' + name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


panel, agent = load('panel'), load('example_agent')


def policy(**changes):
    return dict({'enabled': True, 'billing': 'lifetime_frames', 'metering': 'frames',
                 'frame_limit': 5000, 'expires_at': None, 'period_starts_at': 1000,
                 'period_ends_at': None, 'remaining': 4988, 'charged_frames': 10,
                 'reserved_frames': 2}, **changes)


def quota(**changes):
    return dict({'enabled': True, 'billing': 'lifetime_frames', 'metering': 'frames',
                 'unit': 'successful_frame', 'limit': 5000, 'used': 10, 'reserved': 2,
                 'remaining': 4988, 'expires_at': None, 'terminal_units': 0,
                 'period_starts_at': 1000, 'period_ends_at': None}, **changes)


def receipt(**changes):
    return dict({'activation_id': 'test-activation', 'request_id': 'test-request',
                 'plan_id': 'eh_lifetime', 'billing': 'lifetime_frames', 'months': 0,
                 'frames': 5000, 'total_frames': 5000, 'redeemed_at': 1000}, **changes)


class PermanentSubscriptionTests(unittest.TestCase):
    def state(self, subscription):
        return {'signed_in': True, 'pending': None, 'connection': {'clean': True, 'running': False},
                'cloud_checked_at': self.now, 'credentials': {'api_ready': True, 'device_ready': True,
                                                             'key_id': 'test-key'},
                'cloud': {'subscription': subscription, 'terms': {'current': True},
                          'keys': [{'id': 'test-key', 'revoked': False}],
                          'device': {'registered': True, 'enabled': True}}}

    def setUp(self):
        self.now = time.time() + 10 * 365 * 86400

    def test_permanent_account_is_connectable_years_later(self):
        self.assertEqual(panel.onboarding(self.state(policy()), now=self.now)['stage'], 'connect')

    def test_permanent_zero_balance_and_disabled_still_block_usage(self):
        for changes, expected in (({'remaining': 0}, 'quota'), ({'enabled': False}, 'activation')):
            with self.subTest(expected=expected):
                self.assertEqual(panel.onboarding(self.state(policy(**changes)), now=self.now)['stage'], expected)

    def test_missing_or_malformed_lifetime_fields_do_not_become_permanent(self):
        for changes in ({'billing': None}, {'metering': 'commands'}, {'frame_limit': False},
                        {'frame_limit': 0}, {'expires_at': 1}, {'period_ends_at': 2}):
            self.assertFalse(panel.lifetime_subscription(policy(**changes)), changes)
        for field in ('expires_at', 'period_ends_at'):
            value = policy(); value.pop(field)
            self.assertFalse(panel.lifetime_subscription(value))
        self.assertEqual(panel.onboarding(self.state(policy(billing='calendar_month')), now=self.now)['stage'], 'refresh')

    def test_monthly_expiry_and_positive_balance_keep_existing_behavior(self):
        for expiry, expected in ((self.now + 3600, 'connect'), (self.now - 3600, 'expired')):
            value = policy(billing='calendar_month', expires_at=expiry, period_ends_at=expiry)
            self.assertEqual(panel.onboarding(self.state(value), now=self.now)['stage'], expected)

    def test_permanent_receipt_keeps_total_and_filters_private_fields(self):
        self.assertEqual(panel.Console.activation_receipt(receipt(code='secret-code', token='secret-token')), receipt())

    def test_contradictory_permanent_receipts_are_rejected(self):
        for changes in ({'months': 1}, {'months': False}, {'frames': False}, {'total_frames': 4999},
                        {'total_frames': None}, {'billing': 'calendar_month'}, {'plan_id': 'eh_1m'}):
            with self.subTest(changes=changes), self.assertRaises(panel.PanelError):
                panel.Console.activation_receipt(receipt(**changes))

    def test_old_monthly_receipts_remain_compatible(self):
        value = receipt(plan_id='eh_1m', months=1)
        value.pop('billing'); value.pop('total_frames')
        self.assertEqual(panel.Console.activation_receipt(value), value)

    def test_mcp_quota_preserves_null_dates_and_total_counters(self):
        expected = dict(quota(), available=True)
        actual = agent.subscription_quota(quota(token='private-token'))
        self.assertEqual(actual, expected)
        self.assertEqual(agent._agent_result({'subscription_quota': actual})['subscription_quota'], expected)

    def test_mcp_rejects_malformed_lifetime_contracts(self):
        for changes in ({'billing': 'calendar_month'}, {'expires_at': 1}, {'period_ends_at': 1},
                        {'period_starts_at': None}, {'metering': 'commands'}, {'remaining': 6000}):
            with self.subTest(changes=changes):
                self.assertFalse(agent.subscription_quota(quota(**changes))['available'])
        for field in ('expires_at', 'period_ends_at'):
            value = quota(); value.pop(field)
            self.assertFalse(agent.subscription_quota(value)['available'])

    def test_monthly_mcp_quota_preserves_legacy_shape(self):
        value = quota(expires_at=5000, period_ends_at=5000)
        value.pop('billing')
        self.assertEqual(agent.subscription_quota(value), dict(value, available=True))

    def test_console_refresh_validates_permanent_policy_and_filters_secrets(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as resources:
            store = panel.Store(Path(temporary) / 'data', 'https://example.invalid')
            resources.callback(store.close)
            store.data.update(account='test-account', login_file=store.save_credential({
                'endpoint': 'https://example.invalid', 'token': 'synthetic-login-token-only-' * 2, 'timeout': 1}))
            current_policy = policy(secret='private-policy')
            def remote(_config, _calls):
                return [{'status': 200, 'value': {'account': 'test-account', 'subscription': {
                            'policy': current_policy, 'period_usage': {'remaining': 4988}}}},
                        {'status': 200, 'value': {'keys': []}},
                        {'status': 200, 'value': {'registered': False, 'enabled': False}}]
            app = panel.Console(store, remote_fn=remote)
            app.refresh()
            self.assertEqual(app.cloud['subscription']['billing'], 'lifetime_frames')
            self.assertIsNone(app.cloud['subscription']['expires_at'])
            self.assertNotIn('private-policy', json.dumps(app.cloud))
            current_policy['frame_limit'] = False
            with self.assertRaisesRegex(panel.PanelError, 'invalid_remote_response'):
                app.refresh()


if __name__ == '__main__':
    unittest.main()

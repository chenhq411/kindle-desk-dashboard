import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.collectors.codex import collect


class ProtocolTests(unittest.TestCase):
    def process(self, responses):
        return SimpleNamespace(stdout=io.StringIO(''.join(json.dumps(row) + '\n' for row in responses)),
                               stdin=io.StringIO(), poll=lambda: 0)

    def test_official_handshake_and_allowlisted_summary_exclude_identity(self):
        process = self.process([
            {'id': 1, 'result': {'userAgent': 'fixture'}},
            {'id': 2, 'result': {'account': {'type': 'chatgpt', 'email': 'private-fixture@example.invalid'}}},
            {'id': 3, 'result': {'accountId': 'private-account-fixture', 'rateLimits': {'primary': {'usedPercent': 40, 'windowDurationMins': 300}}}},
        ])
        with patch('app.collectors.codex.discover_executable', return_value='fixture.exe'), patch('subprocess.Popen', return_value=process):
            result = collect(timeout=2)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['buckets'][0]['windows'][0]['remaining_percent'], 60)
        self.assertNotIn('private-', json.dumps(result))

    def test_raw_auth_error_is_never_returned(self):
        process = self.process([
            {'id': 1, 'result': {}},
            {'id': 2, 'error': {'code': -32000, 'message': 'auth expired token=PRIVATE_TEST_VALUE'}},
        ])
        with patch('app.collectors.codex.discover_executable', return_value='fixture.exe'), patch('subprocess.Popen', return_value=process):
            result = collect(timeout=2)
        self.assertEqual(result['status'], 'authentication_required')
        self.assertNotIn('PRIVATE_TEST_VALUE', json.dumps(result))
        self.assertEqual(result['failed_method'], 'account/read')

    def test_api_key_account_does_not_request_paid_usage(self):
        process = self.process([
            {'id': 1, 'result': {}},
            {'id': 2, 'result': {'account': {'type': 'apiKey'}}},
        ])
        with patch('app.collectors.codex.discover_executable', return_value='fixture.exe'), patch('subprocess.Popen', return_value=process):
            result = collect(timeout=2)
        self.assertEqual(result['status'], 'unsupported_account')


if __name__ == '__main__':
    unittest.main()

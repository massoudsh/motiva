import json
import unittest

from integration import decode_event, signature, valid_signature, validate_event


class IntegrationTests(unittest.TestCase):
    def test_versioned_event_and_signature(self):
        event = {'id': 'evt-1', 'type': 'transport_request.created', 'version': 1, 'occurred_at': '2026-11-05T00:00:00Z', 'data': {'origin': 'A'}}
        body = json.dumps(event).encode()
        self.assertTrue(validate_event(event))
        self.assertTrue(valid_signature(body, signature(body, 'test-secret'), 'test-secret'))
        self.assertEqual(decode_event(body)['id'], 'evt-1')

    def test_invalid_event_is_rejected(self):
        self.assertFalse(validate_event({'id': 'evt-1', 'type': 'unknown', 'version': 1, 'occurred_at': 'now', 'data': {}}))
        self.assertIsNone(decode_event(b'{'))


if __name__ == '__main__':
    unittest.main()

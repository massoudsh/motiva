import unittest

from queueing import mission_number, order_missions


class QueueOrderingTests(unittest.TestCase):
    def test_priority_beats_deadline(self):
        queue = order_missions([
            {'id': 'M-1', 'priority': 'low', 'deadline': '2026-01-01'},
            {'id': 'M-2', 'priority': 'urgent', 'deadline': '2026-12-31'},
        ])
        self.assertEqual([item['id'] for item in queue], ['M-2', 'M-1'])

    def test_deadline_breaks_priority_ties_and_missing_deadline_sorts_last(self):
        queue = order_missions([
            {'id': 'M-1', 'priority': 'high', 'deadline': None},
            {'id': 'M-2', 'priority': 'high', 'deadline': '2026-06-01'},
            {'id': 'M-3', 'priority': 'high', 'deadline': '2026-05-01'},
        ])
        self.assertEqual([item['id'] for item in queue], ['M-3', 'M-2', 'M-1'])

    def test_equal_missions_follow_creation_order_numerically(self):
        queue = order_missions([
            {'id': 'M-1000', 'priority': 'normal'},
            {'id': 'M-999', 'priority': 'normal'},
        ])
        self.assertEqual([item['id'] for item in queue], ['M-999', 'M-1000'])
        self.assertEqual(mission_number('M-2049'), 2049)
        self.assertEqual(mission_number('?'), 0)

    def test_unknown_priority_is_treated_as_normal(self):
        queue = order_missions([
            {'id': 'M-1', 'priority': 'bogus'},
            {'id': 'M-2', 'priority': 'low'},
        ])
        self.assertEqual([item['id'] for item in queue], ['M-1', 'M-2'])


if __name__ == '__main__':
    unittest.main()

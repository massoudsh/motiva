import unittest

from analytics import summarize


class AnalyticsTests(unittest.TestCase):
    def test_summary_reports_definitions_and_estimates(self):
        result = summarize(
            mission_statuses={'done': 3, 'running': 1},
            throughput_rows=[{'day': '2026-11-24', 'samples': 120}],
            busy_rows=[{'robot_id': 'R-01', 'samples': 60}],
            robot_count=2,
            days=1,
        )
        self.assertEqual(result['missions']['total'], 4)
        self.assertEqual(result['missions']['completion_rate_percent'], 75)
        self.assertEqual(result['telemetry']['samples'], 120)
        self.assertIn('moving_sample_share_percent', result['fleet'])
        self.assertIn('estimate', result['definitions']['moving_sample_share_percent'])

    def test_empty_fleet_does_not_invent_a_rate(self):
        result = summarize(mission_statuses={}, throughput_rows=[], busy_rows=[], robot_count=0, days=7)
        self.assertIsNone(result['missions']['completion_rate_percent'])
        self.assertIsNone(result['fleet']['moving_sample_share_percent'])


if __name__ == '__main__':
    unittest.main()

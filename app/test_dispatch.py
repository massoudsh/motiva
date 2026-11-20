import unittest

import dispatch


def robot(robot_id, *, status='waiting', battery=80, x=10, y=10, active=0):
    return {'id': robot_id, 'status': status, 'battery': battery, 'position': {'x': x, 'y': y}, 'active_missions': active}


class EligibilityTests(unittest.TestCase):
    def test_stale_offline_and_charging_robots_are_excluded(self):
        result = dispatch.rank_robots([
            robot('R-1', status='offline'),
            robot('R-2', status='charging'),
            robot('R-3', status='moving'),
        ])
        self.assertEqual(result['selected'], 'R-3')
        self.assertEqual(result['eligible_count'], 1)
        reasons = {c['id']: c['reason'] for c in result['candidates']}
        self.assertEqual(reasons['R-1'], 'status_offline')
        self.assertEqual(reasons['R-2'], 'status_charging')

    def test_low_battery_is_excluded_with_a_reason(self):
        result = dispatch.rank_robots([robot('R-1', battery=19), robot('R-2', battery=21)])
        self.assertEqual(result['selected'], 'R-2')
        reasons = {c['id']: c['reason'] for c in result['candidates']}
        self.assertEqual(reasons['R-1'], 'battery_below_threshold')

    def test_unknown_battery_is_excluded_rather_than_assumed(self):
        result = dispatch.rank_robots([robot('R-1', battery=None), robot('R-2')])
        self.assertEqual(result['selected'], 'R-2')
        self.assertEqual(next(c for c in result['candidates'] if c['id'] == 'R-1')['reason'], 'battery_unknown')

    def test_no_eligible_robot_selects_nothing(self):
        result = dispatch.rank_robots([robot('R-1', status='offline')])
        self.assertIsNone(result['selected'])
        self.assertEqual(result['eligible_count'], 0)


class ScoringTests(unittest.TestCase):
    def test_higher_battery_wins_when_everything_else_matches(self):
        result = dispatch.rank_robots([robot('R-1', battery=50), robot('R-2', battery=95)])
        self.assertEqual(result['selected'], 'R-2')

    def test_idle_robot_beats_a_busy_one(self):
        result = dispatch.rank_robots([robot('R-1', active=3), robot('R-2', active=0)])
        self.assertEqual(result['selected'], 'R-2')

    def test_closer_robot_wins_when_origin_is_known(self):
        result = dispatch.rank_robots(
            [robot('R-far', x=90, y=90), robot('R-near', x=11, y=10)],
            origin_position={'x': 10, 'y': 10},
        )
        self.assertEqual(result['selected'], 'R-near')
        self.assertTrue(result['distance_used'])

    def test_distance_is_ignored_when_origin_has_no_position(self):
        result = dispatch.rank_robots([robot('R-1'), robot('R-2')], origin_position=None)
        self.assertFalse(any('distance' in c['components'] for c in result['candidates']))
        self.assertFalse(result['distance_used'])

    def test_malformed_position_disables_distance_but_keeps_the_robot(self):
        broken = {'id': 'R-broken', 'status': 'moving', 'battery': 90, 'position': {'x': True, 'y': 0}, 'active_missions': 0}
        result = dispatch.rank_robots([broken, robot('R-ok', battery=50, x=95, y=95)], origin_position={'x': 10, 'y': 10})
        broken_result = next(c for c in result['candidates'] if c['id'] == 'R-broken')
        self.assertTrue(broken_result['eligible'])
        self.assertNotIn('distance', broken_result['components'])

    def test_ties_break_deterministically_on_id(self):
        first = dispatch.rank_robots([robot('R-b'), robot('R-a')])['selected']
        second = dispatch.rank_robots([robot('R-a'), robot('R-b')])['selected']
        self.assertEqual(first, 'R-a')
        self.assertEqual(second, 'R-a')

    def test_components_are_explainable_and_sum_to_the_score(self):
        result = dispatch.rank_robots([robot('R-1', battery=60, active=1, x=20, y=20)], origin_position={'x': 10, 'y': 10})
        candidate = result['candidates'][0]
        self.assertAlmostEqual(sum(c['contribution'] for c in candidate['components'].values()), candidate['score'], places=4)
        self.assertEqual(set(candidate['components']), {'battery', 'workload', 'distance'})
        for component in candidate['components'].values():
            self.assertGreaterEqual(component['value'], 0)
            self.assertLessEqual(component['value'], 1)

    def test_scores_stay_bounded_with_extreme_inputs(self):
        result = dispatch.rank_robots([robot('R-1', battery=100, active=0, x=0, y=0)], origin_position={'x': 100, 'y': 100})
        candidate = result['candidates'][0]
        self.assertGreaterEqual(candidate['score'], 0)
        self.assertLessEqual(candidate['score'], 1)

    def test_empty_fleet_is_handled(self):
        result = dispatch.rank_robots([])
        self.assertIsNone(result['selected'])
        self.assertEqual(result['candidates'], [])


if __name__ == '__main__':
    unittest.main()

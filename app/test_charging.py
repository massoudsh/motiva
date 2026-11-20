import unittest

import charging


def charger(charger_id, x=None, y=None):
    entry = {'id': charger_id, 'name': charger_id}
    if x is not None:
        entry['position'] = {'x': x, 'y': y}
    return entry


def occupancy(charger_id, robot_id, held_until):
    return {'charger_id': charger_id, 'robot_id': robot_id, 'held_until': held_until}


class ShouldChargeTests(unittest.TestCase):
    def test_healthy_idle_robot_does_not_charge(self):
        self.assertEqual(charging.should_charge(80, status='waiting')['charge'], False)

    def test_low_idle_robot_is_the_cheapest_to_charge(self):
        decision = charging.should_charge(20, status='waiting')
        self.assertTrue(decision['charge'])
        self.assertEqual(decision['reason'], 'idle_below_threshold')

    def test_low_busy_robot_still_charges_but_with_a_distinct_reason(self):
        decision = charging.should_charge(20, status='moving')
        self.assertTrue(decision['charge'])
        self.assertEqual(decision['reason'], 'below_threshold')

    def test_critical_battery_is_flagged_as_critical(self):
        decision = charging.should_charge(3, status='moving')
        self.assertTrue(decision['charge'])
        self.assertEqual(decision['reason'], 'critical')

    def test_offline_charging_and_unknown_robots_are_not_told_to_charge(self):
        self.assertEqual(charging.should_charge(10, status='offline')['reason'], 'status_offline')
        self.assertEqual(charging.should_charge(10, status='charging')['reason'], 'status_charging')
        self.assertEqual(charging.should_charge(None, status='waiting')['reason'], 'battery_unknown')
        self.assertEqual(charging.should_charge(True, status='waiting')['reason'], 'battery_unknown')

    def test_threshold_is_inclusive(self):
        self.assertTrue(charging.should_charge(charging.CHARGE_THRESHOLD, status='waiting')['charge'])
        self.assertFalse(charging.should_charge(charging.CHARGE_THRESHOLD + 1, status='waiting')['charge'])


class ChargerAllocationTests(unittest.TestCase):
    def test_free_charger_is_selected_and_explained(self):
        result = charging.rank_chargers([charger('C1')], [], now=0)
        self.assertEqual(result['selected'], 'C1')
        self.assertIsNone(result['reason'])

    def test_busy_charger_is_excluded(self):
        result = charging.rank_chargers([charger('C1'), charger('C2')], [occupancy('C1', 'R-01', 100)], now=50)
        self.assertEqual(result['selected'], 'C2')
        self.assertEqual(result['busy'], ['C1'])

    def test_expired_occupancy_frees_the_charger(self):
        result = charging.rank_chargers([charger('C1')], [occupancy('C1', 'R-01', 40)], now=50)
        self.assertEqual(result['selected'], 'C1')
        self.assertEqual(result['busy'], [])

    def test_nearest_charger_wins_when_positions_are_known(self):
        result = charging.rank_chargers(
            [charger('C-far', 90, 90), charger('C-near', 12, 11)],
            [], robot_position={'x': 10, 'y': 10}, now=0,
        )
        self.assertEqual(result['selected'], 'C-near')
        self.assertTrue(result['distance_used'])

    def test_all_busy_is_reported_rather_than_guessed(self):
        result = charging.rank_chargers([charger('C1'), charger('C2')], [occupancy('C1', 'R-1', 100), occupancy('C2', 'R-2', 100)], now=0)
        self.assertIsNone(result['selected'])
        self.assertEqual(result['reason'], 'all_chargers_busy')

    def test_no_chargers_configured_is_distinct_from_all_busy(self):
        result = charging.rank_chargers([], [], now=0)
        self.assertIsNone(result['selected'])
        self.assertEqual(result['reason'], 'no_chargers_configured')

    def test_malformed_occupancy_does_not_wedge_a_charger(self):
        bad = [{'charger_id': 'C1', 'held_until': True}, {'charger_id': 'C1', 'held_until': 'soon'}, {'held_until': 999}]
        self.assertEqual(charging.rank_chargers([charger('C1')], bad, now=0)['selected'], 'C1')

    def test_unknown_distance_falls_back_to_id_order(self):
        result = charging.rank_chargers([charger('C-b'), charger('C-a')], [], robot_position=None, now=0)
        self.assertEqual(result['selected'], 'C-a')
        self.assertFalse(result['distance_used'])

    def test_known_distance_is_preferred_over_unknown(self):
        result = charging.rank_chargers(
            [charger('C-unknown'), charger('C-placed', 10, 10)],
            [], robot_position={'x': 10, 'y': 12}, now=0,
        )
        self.assertEqual(result['selected'], 'C-placed')

    def test_malformed_robot_position_disables_distance_only(self):
        result = charging.rank_chargers([charger('C1', 10, 10)], [], robot_position={'x': True, 'y': 0}, now=0)
        self.assertEqual(result['selected'], 'C1')
        self.assertFalse(result['distance_used'])


class LeaseTests(unittest.TestCase):
    def test_lease_sets_expiry(self):
        lease = charging.lease_charger('C1', 'R-01', now=100, seconds=60)
        self.assertEqual(lease, {'charger_id': 'C1', 'robot_id': 'R-01', 'held_until': 160})

    def test_invalid_lease_inputs_are_rejected(self):
        for kwargs in ({'charger_id': '', 'robot_id': 'R-1'}, {'charger_id': 'C1', 'robot_id': ''},
                       {'charger_id': 'C1', 'robot_id': 'R-1', 'seconds': 0},
                       {'charger_id': 'C1', 'robot_id': 'R-1', 'seconds': -5}):
            with self.subTest(kwargs=kwargs):
                self.assertIsNone(charging.lease_charger(now=0, **kwargs))

    def test_leased_charger_is_then_busy_for_another_robot(self):
        lease = charging.lease_charger('C1', 'R-01', now=100, seconds=60)
        result = charging.rank_chargers([charger('C1')], [lease], now=120)
        self.assertIsNone(result['selected'])
        self.assertEqual(result['reason'], 'all_chargers_busy')


if __name__ == '__main__':
    unittest.main()

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


class QueueTests(unittest.TestCase):
    def test_lowest_battery_is_admitted_first(self):
        entries = [charging.queue_entry('R-1', battery=20, requested_at=0), charging.queue_entry('R-2', battery=8, requested_at=50)]
        result = charging.serve_queue(entries, 1, now=100)
        self.assertEqual(result['admit'], ['R-2'])

    def test_no_free_bay_admits_nobody(self):
        entries = [charging.queue_entry('R-1', battery=8, requested_at=0)]
        self.assertEqual(charging.serve_queue(entries, 0, now=100)['admit'], [])

    def test_more_bays_than_waiters_admits_everyone(self):
        entries = [charging.queue_entry('R-1', battery=8, requested_at=0), charging.queue_entry('R-2', battery=9, requested_at=0)]
        result = charging.serve_queue(entries, 5, now=100)
        self.assertEqual(sorted(result['admit']), ['R-1', 'R-2'])
        self.assertEqual(result['waiting'], [])

    def test_critical_robot_jumps_ahead_of_a_lower_but_less_urgent_one(self):
        entries = [charging.queue_entry('R-1', battery=20, requested_at=0), charging.queue_entry('R-2', battery=18, requested_at=5, critical=True)]
        result = charging.serve_queue(entries, 1, now=100)
        self.assertEqual(result['admit'], ['R-2'])

    def test_a_starving_robot_jumps_one_with_a_slightly_lower_battery(self):
        # R-old waited far past the limit with a higher battery; R-new is lower
        # but only just arrived. Starvation protection must win here.
        entries = [
            charging.queue_entry('R-old', battery=24, requested_at=0),
            charging.queue_entry('R-new', battery=20, requested_at=995),
        ]
        result = charging.serve_queue(entries, 1, now=1000)
        self.assertEqual(result['admit'], ['R-old'])
        self.assertTrue(result['waiting'][0]['escalated'] is False)

    def test_a_long_wait_beats_a_marginally_lower_battery(self):
        entries = [
            charging.queue_entry('R-old', battery=22, requested_at=0),      # waited 1000s
            charging.queue_entry('R-new', battery=6, requested_at=990),     # waited 10s
        ]
        result = charging.serve_queue(entries, 1, now=1000)
        self.assertEqual(result['admit'], ['R-old'])

    def test_waited_time_and_escalation_reason_are_reported(self):
        entries = [charging.queue_entry('R-1', battery=10, requested_at=0)]
        entry = charging.serve_queue(entries, 0, now=700)['waiting'][0]
        self.assertEqual(entry['waited_seconds'], 700)
        self.assertTrue(entry['escalated'])
        self.assertEqual(entry['escalation_reason'], 'starving')

    def test_non_escalated_entry_reports_no_reason(self):
        entries = [charging.queue_entry('R-1', battery=10, requested_at=0)]
        entry = charging.serve_queue(entries, 0, now=100)['waiting'][0]
        self.assertFalse(entry['escalated'])
        self.assertIsNone(entry['escalation_reason'])

    def test_ties_break_deterministically(self):
        entries = [charging.queue_entry('R-b', battery=10, requested_at=0), charging.queue_entry('R-a', battery=10, requested_at=0)]
        self.assertEqual(charging.serve_queue(entries, 1, now=100)['admit'], ['R-a'])

    def test_malformed_entries_are_ignored_not_admitted(self):
        entries = [None, 'x', {'robot_id': 'R-1'}, charging.queue_entry('R-2', battery=10, requested_at=0)]
        result = charging.serve_queue(entries, 1, now=100)
        self.assertEqual(result['admit'], ['R-2'])

    def test_malformed_free_bay_count_admits_nobody(self):
        entries = [charging.queue_entry('R-1', battery=10, requested_at=0)]
        self.assertEqual(charging.serve_queue(entries, True, now=100)['admit'], [])

    def test_invalid_queue_entry_inputs_are_rejected(self):
        for kwargs in ({'robot_id': '', 'battery': 10, 'requested_at': 0},
                       {'robot_id': 'R-1', 'battery': True, 'requested_at': 0},
                       {'robot_id': 'R-1', 'battery': 'low', 'requested_at': 0},
                       {'robot_id': 'R-1', 'battery': 10, 'requested_at': None}):
            with self.subTest(kwargs=kwargs):
                self.assertIsNone(charging.queue_entry(**kwargs))

    def test_escalation_lists_only_stuck_robots(self):
        entries = [charging.queue_entry('R-fine', battery=10, requested_at=950), charging.queue_entry('R-stuck', battery=10, requested_at=0)]
        stuck = charging.escalate(entries, now=1000)
        self.assertEqual([entry['robot_id'] for entry in stuck], ['R-stuck'])


if __name__ == '__main__':
    unittest.main()

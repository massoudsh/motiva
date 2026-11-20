import unittest

import traffic


def reservation(node_id, robot_id, held_until, mission_id=1):
    return {'node_id': node_id, 'robot_id': robot_id, 'mission_id': mission_id, 'held_until': held_until}


EDGES = [('A', 'B'), ('B', 'C'), ('A', 'D'), ('D', 'C'), ('C', 'E')]


class ReservationStateTests(unittest.TestCase):
    def test_expired_reservations_are_ignored(self):
        active = traffic.active_reservations([reservation('B', 'R-1', 50), reservation('C', 'R-2', 150)], now=100)
        self.assertEqual([r['node_id'] for r in active], ['C'])

    def test_malformed_expiry_is_treated_as_inactive(self):
        bad = [reservation('B', 'R-1', None), reservation('C', 'R-1', True), reservation('D', 'R-1', 'soon')]
        self.assertEqual(traffic.active_reservations(bad, now=0), [])

    def test_holders_exclude_the_calling_robot(self):
        reservations = [reservation('B', 'R-1', 200), reservation('C', 'R-2', 200)]
        holders = traffic.holders_by_node(reservations, now=100, exclude_robot='R-1')
        self.assertEqual(holders, {'C': 'R-2'})


class RoutePlanningTests(unittest.TestCase):
    def test_clear_route_reports_no_traffic_influence(self):
        result = traffic.plan_route(EDGES, 'A', 'C', now=0)
        self.assertEqual(result['path'], ['A', 'B', 'C'])
        self.assertEqual(result['status'], 'clear')
        self.assertFalse(result['traffic_applied'])
        self.assertEqual(result['blocked_nodes'], [])

    def test_another_robots_lease_forces_a_detour(self):
        result = traffic.plan_route(
            EDGES, 'A', 'C', reservations=[reservation('B', 'R-2', 200)], robot_id='R-1', now=100,
        )
        self.assertEqual(result['path'], ['A', 'D', 'C'])
        self.assertEqual(result['status'], 'detoured')
        self.assertTrue(result['traffic_applied'])
        self.assertEqual(result['reserved_by'], {'B': 'R-2'})

    def test_a_robot_is_not_blocked_by_its_own_lease(self):
        result = traffic.plan_route(
            EDGES, 'A', 'C', reservations=[reservation('B', 'R-1', 200)], robot_id='R-1', now=100,
        )
        self.assertEqual(result['path'], ['A', 'B', 'C'])
        self.assertEqual(result['status'], 'clear')

    def test_expired_lease_does_not_affect_routing(self):
        result = traffic.plan_route(
            EDGES, 'A', 'C', reservations=[reservation('B', 'R-2', 50)], robot_id='R-1', now=100,
        )
        self.assertEqual(result['path'], ['A', 'B', 'C'])
        self.assertFalse(result['traffic_applied'])

    def test_no_route_and_blocked_by_traffic_are_distinguished(self):
        no_route = traffic.plan_route([('A', 'B')], 'A', 'Z', now=0)
        self.assertEqual(no_route['status'], 'no_route')
        self.assertEqual(no_route['path'], [])

        # B is the only way through, so traffic is the reason, not the map.
        by_traffic = traffic.plan_route(
            [('A', 'B'), ('B', 'C')], 'A', 'C',
            reservations=[reservation('B', 'R-2', 200)], robot_id='R-1', now=100,
        )
        self.assertEqual(by_traffic['status'], 'blocked_by_traffic')
        self.assertEqual(by_traffic['path'], [])

    def test_permanent_obstacles_and_traffic_combine(self):
        # `D` blocked leaves A-B-C-E as the only permanent route, so the lease on
        # `B` is what finally severs it — the verdict must blame traffic, not the map.
        result = traffic.plan_route(
            EDGES, 'A', 'E', blocked={'D'}, reservations=[reservation('B', 'R-2', 200)],
            robot_id='R-1', now=100,
        )
        self.assertEqual(result['status'], 'blocked_by_traffic')
        self.assertEqual(result['path'], [])

        # With no permanent route at all, traffic is not the reason.
        no_map_route = traffic.plan_route(
            EDGES, 'A', 'E', blocked={'B', 'D'}, reservations=[reservation('C', 'R-2', 200)],
            robot_id='R-1', now=100,
        )
        self.assertEqual(no_map_route['status'], 'no_route')

    def test_endpoints_are_reachable_even_when_reserved(self):
        result = traffic.plan_route(
            EDGES, 'A', 'C', reservations=[reservation('C', 'R-9', 200), reservation('A', 'R-8', 200)],
            robot_id='R-1', now=100,
        )
        self.assertEqual(result['path'], ['A', 'B', 'C'])


class LeaseTests(unittest.TestCase):
    def test_lease_covers_transit_nodes_only(self):
        leases = traffic.lease_path(['A', 'B', 'C', 'D', 'E'], robot_id='R-1', mission_id=7, now=100, depth=3, seconds=30)
        # A and E are stations, so only the corridor between them is leased.
        self.assertEqual([lease['node_id'] for lease in leases], ['B', 'C', 'D'])
        self.assertTrue(all(lease['held_until'] == 130 for lease in leases))
        self.assertTrue(all(lease['robot_id'] == 'R-1' and lease['mission_id'] == 7 for lease in leases))

    def test_two_station_path_leases_nothing_because_endpoints_are_shared(self):
        self.assertEqual(traffic.lease_path(['A', 'B'], robot_id='R-1', mission_id=1, now=0), [])

    def test_endpoints_can_be_leased_explicitly(self):
        leases = traffic.lease_path(['A', 'B', 'C'], robot_id='R-1', mission_id=1, now=0, include_endpoints=True)
        self.assertEqual([lease['node_id'] for lease in leases], ['A', 'B', 'C'])

    def test_lease_depth_is_bounded_by_transit_length(self):
        leases = traffic.lease_path(['A', 'B', 'C', 'D'], robot_id='R-1', mission_id=1, now=0, depth=10)
        self.assertEqual([lease['node_id'] for lease in leases], ['B', 'C'])

    def test_invalid_lease_inputs_produce_no_reservation(self):
        for kwargs in (
            {'robot_id': '', 'mission_id': 1},
            {'robot_id': 'R-1', 'mission_id': 1, 'depth': 0},
            {'robot_id': 'R-1', 'mission_id': 1, 'depth': -1},
            {'robot_id': 'R-1', 'mission_id': 1, 'seconds': 0},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(traffic.lease_path(['A', 'B', 'C'], now=0, **kwargs), [])
        self.assertEqual(traffic.lease_path([], robot_id='R-1', mission_id=1, now=0), [])

    def test_leased_corridor_forces_another_robot_to_detour(self):
        leases = traffic.lease_path(['A', 'B', 'C'], robot_id='R-1', mission_id=1, now=100, depth=2, seconds=60)
        result = traffic.plan_route(EDGES, 'A', 'C', reservations=leases, robot_id='R-2', now=120)
        self.assertEqual(result['status'], 'detoured')
        self.assertEqual(result['path'], ['A', 'D', 'C'])


class ConflictTests(unittest.TestCase):
    def test_duplicate_active_holders_are_reported(self):
        reservations = [reservation('B', 'R-1', 200), reservation('B', 'R-2', 200), reservation('C', 'R-3', 200)]
        conflicts = traffic.find_conflicts(reservations, now=100)
        self.assertEqual(conflicts, [{'node_id': 'B', 'robots': ['R-1', 'R-2']}])

    def test_expired_duplicates_are_not_conflicts(self):
        reservations = [reservation('B', 'R-1', 50), reservation('B', 'R-2', 50)]
        self.assertEqual(traffic.find_conflicts(reservations, now=100), [])


if __name__ == '__main__':
    unittest.main()

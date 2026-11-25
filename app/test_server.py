import concurrent.futures
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

import server


class OperationsFixture(unittest.TestCase):
    """Shared harness: temp database, live HTTP server, heartbeat helpers."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.original_path = server.DB_PATH
        server.DB_PATH = Path(self.temp.name) / 'test.sqlite3'
        server.initialize_db()
        self.heartbeat_all()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever)
        self.thread.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.DB_PATH = self.original_path
        self.temp.cleanup()

    def post(self, path, payload=None, raw=None):
        body = json.dumps(payload).encode() if raw is None else raw
        client = http.client.HTTPConnection(*self.http.server_address, timeout=5)
        try:
            client.request('POST', path, body, {'Content-Type': 'application/json'})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def get(self, path):
        client = http.client.HTTPConnection(*self.http.server_address, timeout=5)
        try:
            client.request('GET', path)
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def create(self, number=0):
        return self.post('/api/missions', {'origin': f'Origin {number}', 'destination': 'Destination'})

    def heartbeat_all(self, age=0):
        """Give every seeded robot a fresh heartbeat so it is not stale."""
        with sqlite3.connect(server.DB_PATH) as db:
            db.execute('UPDATE robots SET heartbeat_at = ?', (time.time() - age,))


class OperationsTests(OperationsFixture):
    def test_active_total_is_not_limited_to_recent_rows(self):
        for number in range(15):
            self.assertEqual(self.create(number)[0], 201)
        data = server.response_payload()
        self.assertEqual(len(data['missions']['items']), 10)
        self.assertEqual(data['missions']['active'], 17)

    def test_concurrent_creation_has_unique_ids(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(self.create, range(18)))
        self.assertEqual([status for status, _ in results], [201] * 18)
        self.assertEqual(len({data['mission']['id'] for _, data in results}), 18)

    def test_concurrent_assignment_has_only_one_winner(self):
        def assign(robot):
            return self.post('/api/missions/2046/assign', {'robot': robot})[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(assign, ['R-01', 'R-04']))
        self.assertEqual(sorted(statuses), [200, 409])

    def test_telemetry_rejects_invalid_types_and_coordinates(self):
        valid = {'id': 'R-07', 'status': 'moving', 'battery': 70, 'position': {'x': 30, 'y': 50}}
        for changes in ({'status': []}, {'status': {}}, {'battery': True},
                        {'position': {'x': True, 'y': 50}},
                        {'position': {'x': -1, 'y': 50}},
                        {'position': {'x': 30, 'y': 101}},
                        {'position': {'x': 2**100, 'y': 50}}):
            with self.subTest(changes=changes):
                self.assertEqual(self.post('/api/telemetry', {**valid, **changes})[0], 422)
        self.assertEqual(self.post('/api/telemetry', valid)[0], 200)

    def test_malformed_json_is_a_client_error(self):
        for path in ('/api/missions', '/api/telemetry', '/api/missions/2046/cancel'):
            for raw in (b'{', b'\xff', b'', b'null', b' ' * 65537):
                with self.subTest(path=path, raw_length=len(raw)):
                    self.assertEqual(self.post(path, raw=raw)[0], 400)

    def test_cancel_and_assign_conflicts(self):
        self.assertEqual(self.post('/api/missions/2046/assign', {'robot': 'missing'})[0], 422)
        self.assertEqual(self.post('/api/missions/2046/cancel', {})[0], 200)
        self.assertEqual(self.post('/api/missions/2046/cancel', {})[0], 409)
        self.assertEqual(self.post('/api/missions/2047/cancel', {})[0], 409)
        status, data = self.post('/api/missions/2046/assign', {'robot': 'R-04'})
        self.assertEqual(status, 200)
        self.assertEqual(data['mission']['status'], 'running')

    def test_legacy_migration_and_restart_preserve_data(self):
        legacy_path = Path(self.temp.name) / 'legacy.sqlite3'
        with sqlite3.connect(legacy_path) as db:
            db.execute("""CREATE TABLE missions (id INTEGER PRIMARY KEY, origin TEXT NOT NULL,
                destination TEXT NOT NULL, robot TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('done', 'running', 'waiting')),
                started_at TEXT NOT NULL)""")
            db.execute("INSERT INTO missions VALUES (3000, 'Origin', 'Destination', 'R-01', 'waiting', '09:00')")
        server.DB_PATH = legacy_path
        server.initialize_db()
        server.initialize_db()
        self.assertEqual([item['id'] for item in server.response_payload()['missions']['items']], ['M-3000'])
        self.assertEqual(self.post('/api/missions/3000/cancel', {})[0], 200)
        server.initialize_db()
        self.assertEqual(server.response_payload()['missions']['items'][0]['status'], 'cancelled')
    def test_mission_details_are_persisted(self):
        status, data = self.post('/api/missions', {'origin': 'A', 'destination': 'B', 'cargo': 'Pallet', 'priority': 'urgent', 'deadline': '18:00', 'source': 'wms'})
        self.assertEqual(status, 201)
        self.assertEqual(data['mission']['priority'], 'urgent')
        self.assertEqual(data['mission']['source'], 'wms')
        self.assertEqual(data['mission']['cargo'], 'Pallet')

    def test_alerts_reports_and_telemetry_history(self):
        self.assertEqual(self.post('/api/telemetry', {'id': 'R-01', 'status': 'moving', 'battery': 15, 'position': {'x': 30, 'y': 40}})[0], 200)
        status, alerts = self.get('/api/alerts')
        self.assertEqual(status, 200)
        self.assertEqual(alerts['alerts'][0]['type'], 'low_battery')
        status, report = self.get('/api/reports')
        self.assertEqual(status, 200)
        self.assertEqual(report['telemetry_samples'], 1)

    def test_map_route_respects_temporary_obstacles(self):
        for node in (
            {'id': 'A', 'kind': 'station', 'name': 'A'},
            {'id': 'B', 'kind': 'zone', 'name': 'B'},
            {'id': 'C', 'kind': 'station', 'name': 'C'},
            {'id': 'D', 'kind': 'zone', 'name': 'D'},
        ):
            self.assertEqual(self.post('/api/map/nodes', node)[0], 201)
        for edge in ({'source': 'A', 'target': 'B'}, {'source': 'B', 'target': 'C'}, {'source': 'A', 'target': 'D'}, {'source': 'D', 'target': 'C'}):
            self.assertEqual(self.post('/api/map/edges', edge)[0], 201)
        self.assertEqual(self.post('/api/map/route', {'start': 'A', 'goal': 'C'})[1]['path'], ['A', 'B', 'C'])
        self.assertEqual(self.post('/api/map/obstacles', {'node_id': 'B', 'active': True})[0], 200)
        self.assertEqual(self.post('/api/map/route', {'start': 'A', 'goal': 'C'})[1]['path'], ['A', 'D', 'C'])


class HeartbeatTests(OperationsFixture):
    """Offline is derived from heartbeat freshness, not from a stored flag."""

    def test_robot_without_heartbeat_is_offline_and_not_assignable(self):
        with sqlite3.connect(server.DB_PATH) as db:
            db.execute("UPDATE robots SET heartbeat_at = NULL")
        self.assertEqual(self.post('/api/missions/2046/assign', {'robot': 'R-04'})[0], 409)
        _, alerts = self.get('/api/alerts')
        self.assertTrue(any(alert['type'] == 'robot_offline' for alert in alerts['alerts']))

    def test_stale_heartbeat_marks_offline_but_fresh_heartbeat_does_not(self):
        self.heartbeat_all(age=server.HEARTBEAT_TIMEOUT_SECONDS + 5)
        data = server.response_payload()
        self.assertTrue(all(robot['stale'] for robot in data['robots']))
        self.assertEqual(data['fleet']['online'], 0)
        self.assertEqual(self.post('/api/missions/2046/assign', {'robot': 'R-04'})[0], 409)

        self.heartbeat_all()
        data = server.response_payload()
        self.assertFalse(any(robot['stale'] for robot in data['robots']))
        self.assertEqual(data['fleet']['online'], data['fleet']['total'])
        self.assertEqual(self.post('/api/missions/2046/assign', {'robot': 'R-04'})[0], 200)

    def test_http_telemetry_counts_as_a_heartbeat(self):
        with sqlite3.connect(server.DB_PATH) as db:
            db.execute("UPDATE robots SET heartbeat_at = NULL WHERE id = 'R-07'")
        self.assertEqual(self.post('/api/telemetry', {'id': 'R-07', 'status': 'moving', 'battery': 60, 'position': {'x': 10, 'y': 10}})[0], 200)
        robot = next(item for item in server.response_payload()['robots'] if item['id'] == 'R-07')
        self.assertFalse(robot['stale'])

    def test_reported_status_is_preserved_alongside_derived_offline(self):
        with sqlite3.connect(server.DB_PATH) as db:
            db.execute("UPDATE robots SET heartbeat_at = NULL WHERE id = 'R-01'")
        robot = next(item for item in server.response_payload()['robots'] if item['id'] == 'R-01')
        self.assertEqual(robot['status'], 'offline')
        self.assertEqual(robot['reported_status'], 'moving')


class VdaBridgeTests(OperationsFixture):
    def state(self, **overrides):
        base = {
            'orderId': '', 'orderUpdateId': 0, 'lastNodeSequenceId': 0,
            'nodeStates': [], 'edgeStates': [], 'actionStates': [],
            'batteryState': {'batteryCharge': 55.6},
            'agvPosition': {'x': 30.0, 'y': 40.0, 'positionInitialized': True},
            'operatingMode': 'AUTOMATIC',
            'safetyState': {'eStop': 'NONE', 'fieldViolation': False},
            'errors': [],
        }
        base.update(overrides)
        return base

    def send(self, **payload):
        return self.post('/api/integrations/vda5050', payload)

    def test_state_message_updates_robot_and_records_history(self):
        status, data = self.send(agv_id='R-07', message_type='state', payload=self.state())
        self.assertEqual(status, 200)
        self.assertEqual(data['telemetry']['status'], 'waiting')
        self.assertEqual(data['telemetry']['battery'], 56)
        robot = next(item for item in server.response_payload()['robots'] if item['id'] == 'R-07')
        self.assertEqual(robot['battery'], 56)
        self.assertEqual(robot['position'], {'x': 30, 'y': 40})
        self.assertFalse(robot['stale'])
        _, report = self.get('/api/reports')
        self.assertEqual(report['telemetry_samples'], 1)

    def test_open_order_sets_moving_and_order_context(self):
        self.send(agv_id='R-07', message_type='state', payload=self.state(orderId='ord-9'))
        robot = next(item for item in server.response_payload()['robots'] if item['id'] == 'R-07')
        self.assertEqual(robot['status'], 'moving')
        self.assertEqual(robot['order_id'], 'ord-9')

    def test_safety_state_raises_alerts(self):
        self.send(agv_id='R-07', message_type='state', payload=self.state(safetyState={'eStop': 'REMOTE', 'fieldViolation': True}))
        _, alerts = self.get('/api/alerts')
        types = {alert['type'] for alert in alerts['alerts']}
        self.assertIn('emergency_stop', types)
        self.assertIn('protective_field', types)

    def test_explicit_offline_connection_drops_heartbeat(self):
        self.send(agv_id='R-07', message_type='connection', payload={'connectionState': 'ONLINE'})
        self.assertFalse(next(r for r in server.response_payload()['robots'] if r['id'] == 'R-07')['stale'])
        status, data = self.send(agv_id='R-07', message_type='connection', payload={'connectionState': 'CONNECTIONBROKEN'})
        self.assertEqual(status, 200)
        self.assertFalse(data['online'])
        self.assertTrue(next(r for r in server.response_payload()['robots'] if r['id'] == 'R-07')['stale'])

    def test_bridge_rejects_bad_envelopes_and_unknown_robots(self):
        self.assertEqual(self.send(agv_id='', message_type='state', payload=self.state())[0], 422)
        self.assertEqual(self.send(agv_id='R-07', message_type='order', payload={})[0], 422)
        self.assertEqual(self.send(agv_id='R-07', message_type='state', payload={'batteryState': {}})[0], 422)
        self.assertEqual(self.send(agv_id='R-07', message_type='connection', payload={'connectionState': 'MAYBE'})[0], 422)
        self.assertEqual(self.send(agv_id='R-99', message_type='state', payload=self.state())[0], 404)

    def test_bridge_requires_no_webhook_secret(self):
        # The VDA bridge is a separate surface from the signed WMS webhook.
        self.assertEqual(self.send(agv_id='R-07', message_type='state', payload=self.state())[0], 200)


class DispatchEndpointTests(OperationsFixture):
    def place(self, node_id, x, y):
        return self.post('/api/map/nodes', {'id': node_id, 'kind': 'station', 'name': node_id, 'x': x, 'y': y})

    def test_preview_explains_the_choice_without_assigning(self):
        status, data = self.get('/api/missions/2046/dispatch')
        self.assertEqual(status, 200)
        self.assertIsNotNone(data['dispatch']['selected'])
        self.assertTrue(data['dispatch']['candidates'])
        self.assertEqual(data['mission']['status'], 'waiting')
        for candidate in data['dispatch']['candidates']:
            self.assertEqual(set(candidate), {'id', 'eligible', 'score', 'reason', 'components'})

    def test_auto_assign_picks_the_best_robot_and_reports_why(self):
        status, data = self.post('/api/missions/2046/assign', {'auto': True})
        self.assertEqual(status, 200)
        self.assertEqual(data['mission']['status'], 'running')
        self.assertEqual(data['mission']['robot'], data['dispatch']['selected'])
        self.assertEqual(data['dispatch']['candidates'][0]['id'], data['dispatch']['selected'])

    def test_auto_assign_without_eligible_robots_is_a_conflict(self):
        self.heartbeat_all(age=server.HEARTBEAT_TIMEOUT_SECONDS + 5)
        status, data = self.post('/api/missions/2046/assign', {'auto': True})
        self.assertEqual(status, 409)
        self.assertEqual(data['error'], 'no_eligible_robot')
        self.assertIsNone(data['dispatch']['selected'])

    def test_distance_is_used_only_when_origin_names_a_placed_node(self):
        self.place('A', 10, 10)
        status, data = self.get('/api/missions/2046/dispatch')
        self.assertEqual(status, 200)
        # Seed mission origin is free text, so no distance signal is available.
        self.assertFalse(data['dispatch']['distance_used'])
        self.assertIsNone(data['dispatch']['origin_position'])

        created = self.post('/api/missions', {'origin': 'A', 'destination': 'B'})[1]
        status, data = self.get(f"/api/missions/{created['mission']['id'][2:]}/dispatch")
        self.assertTrue(data['dispatch']['distance_used'])
        self.assertEqual(data['dispatch']['origin_position'], {'x': 10, 'y': 10})

    def test_manual_assign_still_works_and_has_no_dispatch_key(self):
        status, data = self.post('/api/missions/2046/assign', {'robot': 'R-04'})
        self.assertEqual(status, 200)
        self.assertNotIn('dispatch', data)

    def test_assign_with_neither_robot_nor_auto_is_rejected(self):
        self.assertEqual(self.post('/api/missions/2046/assign', {})[0], 422)
        self.assertEqual(self.post('/api/missions/2046/assign', {'auto': 'yes'})[0], 422)

    def test_dispatch_preview_rejects_non_waiting_mission(self):
        self.assertEqual(self.get('/api/missions/2047/dispatch')[0], 409)
        self.assertEqual(self.get('/api/missions/999999/dispatch')[0], 404)

    def test_node_coordinates_validate_and_survive_re_add(self):
        self.assertEqual(self.place('A', 10, 10)[0], 201)
        # Re-adding without coordinates must not erase the placed position.
        self.assertEqual(self.post('/api/map/nodes', {'id': 'A', 'kind': 'station', 'name': 'A'})[0], 201)
        _, data = self.post('/api/missions', {'origin': 'A', 'destination': 'B'})
        _, preview = self.get(f"/api/missions/{data['mission']['id'][2:]}/dispatch")
        self.assertEqual(preview['dispatch']['origin_position'], {'x': 10, 'y': 10})

    def test_partial_or_out_of_range_coordinates_are_rejected(self):
        for payload in ({'x': 10}, {'y': 10}, {'x': -1, 'y': 10}, {'x': 101, 'y': 10}, {'x': True, 'y': 10}, {'x': '10', 'y': 10}):
            with self.subTest(payload=payload):
                self.assertEqual(self.post('/api/map/nodes', {'id': 'A', 'kind': 'station', 'name': 'A', **payload})[0], 422)


class TrafficEndpointTests(OperationsFixture):
    def build(self):
        for node in ({'id': 'A', 'x': 10, 'y': 10}, {'id': 'B', 'x': 30, 'y': 10},
                     {'id': 'C', 'x': 50, 'y': 10}, {'id': 'D', 'x': 30, 'y': 40}):
            self.assertEqual(self.post('/api/map/nodes', {'kind': 'station', 'name': node['id'], **node})[0], 201)
        for edge in ({'source': 'A', 'target': 'B'}, {'source': 'B', 'target': 'C'},
                     {'source': 'A', 'target': 'D'}, {'source': 'D', 'target': 'C'}):
            self.assertEqual(self.post('/api/map/edges', edge)[0], 201)

    def route(self, **payload):
        return self.post('/api/map/route', payload)

    def test_route_without_traffic_keeps_the_existing_response_shape(self):
        self.build()
        status, data = self.route(start='A', goal='C')
        self.assertEqual(status, 200)
        self.assertEqual(data['path'], ['A', 'B', 'C'])
        self.assertFalse(data['traffic']['traffic_applied'])

    def test_reserve_requires_a_robot(self):
        self.build()
        self.assertEqual(self.route(start='A', goal='C', reserve=True)[0], 422)

    def test_reserved_route_forces_the_second_robot_to_avoid_the_corridor(self):
        self.build()
        status, first = self.route(start='A', goal='C', robot='R-01', reserve=True)
        self.assertEqual(status, 200)
        self.assertEqual(first['path'], ['A', 'B', 'C'])
        # Stations are shared; only the corridor between them is leased.
        self.assertEqual(first['leased_nodes'], ['B'])

        status, second = self.route(start='A', goal='C', robot='R-04', reserve=True)
        self.assertEqual(status, 200)
        self.assertEqual(second['path'], ['A', 'D', 'C'])
        self.assertTrue(second['traffic']['traffic_applied'])
        self.assertEqual(second['traffic']['reserved_by']['B'], 'R-01')

    def test_a_robot_is_not_blocked_by_its_own_reservation(self):
        self.build()
        self.assertEqual(self.route(start='A', goal='C', robot='R-01', reserve=True)[0], 200)
        status, again = self.route(start='A', goal='C', robot='R-01', reserve=True)
        self.assertEqual(status, 200)
        self.assertEqual(again['path'], ['A', 'B', 'C'])

    def test_traffic_blocked_route_reports_the_reason(self):
        self.build()
        # A-D-C is cut, so B is the only corridor between A and C.
        self.post('/api/map/obstacles', {'node_id': 'D', 'active': True})
        self.assertEqual(self.route(start='A', goal='C', robot='R-01', reserve=True)[0], 200)
        status, data = self.route(start='A', goal='C', robot='R-04')
        self.assertEqual(status, 409)
        self.assertEqual(data['error'], 'blocked_by_traffic')
        self.assertEqual(data['traffic']['reserved_by'], {'B': 'R-01'})

    def test_map_exposes_active_reservations_and_conflicts(self):
        self.build()
        self.route(start='A', goal='C', robot='R-01', reserve=True)
        status, data = self.get('/api/map')
        self.assertEqual(status, 200)
        self.assertEqual({r['node_id'] for r in data['reservations']}, {'B'})
        self.assertEqual(data['conflicts'], [])

    def test_mission_assignment_leases_the_corridor_and_cancel_releases_it(self):
        self.build()
        created = self.post('/api/missions', {'origin': 'A', 'destination': 'C'})[1]
        mission_id = created['mission']['id'][2:]
        status, data = self.post(f'/api/missions/{mission_id}/assign', {'robot': 'R-01'})
        self.assertEqual(status, 200)
        # Only the transit node is exclusive; the shared stations are not.
        self.assertEqual(data['traffic']['leased_nodes'], ['B'])

        _, map_data = self.get('/api/map')
        self.assertEqual({r['node_id'] for r in map_data['reservations']}, {'B'})

        # A second mission through the same corridor is detoured, not refused.
        second = self.post('/api/missions', {'origin': 'A', 'destination': 'C'})[1]
        second_id = second['mission']['id'][2:]
        _, assigned = self.post(f'/api/missions/{second_id}/assign', {'robot': 'R-04'})
        self.assertTrue(assigned['traffic']['traffic_applied'])
        self.assertEqual(assigned['traffic']['leased_nodes'], ['D'])

        # Cancelling a waiting mission releases its lease and reports it.
        pending = self.post('/api/missions', {'origin': 'A', 'destination': 'D'})[1]
        cancel_id = pending['mission']['id'][2:]
        self.assertEqual(self.post(f'/api/missions/{cancel_id}/cancel', {})[0], 200)
        status, cancelled = self.post(f'/api/missions/{cancel_id}/cancel', {})
        self.assertEqual(status, 409)

    def test_mission_with_free_text_endpoints_is_reported_as_unrouted(self):
        created = self.post('/api/missions', {'origin': 'Loading dock', 'destination': 'Line A'})[1]
        status, data = self.post(f"/api/missions/{created['mission']['id'][2:]}/assign", {'robot': 'R-01'})
        self.assertEqual(status, 200)
        self.assertEqual(data['traffic']['status'], 'unrouted')
        self.assertEqual(data['traffic']['leased_nodes'], [])

    def test_expired_lease_frees_the_corridor(self):
        self.build()
        self.route(start='A', goal='C', robot='R-01', reserve=True)
        with sqlite3.connect(server.DB_PATH) as db:
            db.execute('UPDATE node_reservations SET held_until = ?', (time.time() - 1,))
        status, data = self.route(start='A', goal='C', robot='R-04')
        self.assertEqual(status, 200)
        self.assertFalse(data['traffic']['traffic_applied'])


class ChargingEndpointTests(OperationsFixture):
    def drain(self, robot_id, battery):
        return self.post('/api/telemetry', {'id': robot_id, 'status': 'waiting', 'battery': battery, 'position': {'x': 10, 'y': 10}})

    def add(self, charger_id, **coords):
        return self.post('/api/chargers', {'id': charger_id, 'name': charger_id, **coords})

    def test_charger_can_be_registered_and_listed(self):
        self.assertEqual(self.add('C1', x=20, y=30)[0], 201)
        status, data = self.get('/api/chargers')
        self.assertEqual(status, 200)
        self.assertEqual(data['chargers'][0]['position'], {'x': 20, 'y': 30})
        self.assertEqual(data['occupancies'], [])

    def test_invalid_charger_payloads_are_rejected(self):
        for payload in ({}, {'id': ''}, {'id': 'C1', 'x': 10}, {'id': 'C1', 'x': -1, 'y': 10}, {'id': 'C1', 'x': True, 'y': 10}):
            with self.subTest(payload=payload):
                self.assertEqual(self.post('/api/chargers', payload)[0], 422)

    def test_healthy_robot_is_not_sent_to_charge(self):
        self.add('C1')
        status, data = self.get('/api/robots/R-01/charge')
        self.assertEqual(status, 200)
        self.assertFalse(data['charge'])
        self.assertEqual(data['reason'], 'battery_sufficient')
        self.assertEqual(self.post('/api/robots/R-01/charge', {})[0], 409)

    def test_low_robot_is_assigned_a_free_charger(self):
        self.add('C1')
        self.drain('R-01', 15)
        status, data = self.post('/api/robots/R-01/charge', {})
        self.assertEqual(status, 200)
        self.assertEqual(data['charger'], 'C1')
        self.assertEqual(data['robot']['status'], 'charging')

        _, listing = self.get('/api/chargers')
        self.assertEqual([(o['charger_id'], o['robot_id']) for o in listing['occupancies']], [('C1', 'R-01')])

    def test_second_robot_cannot_take_an_occupied_charger(self):
        self.add('C1')
        self.drain('R-01', 15)
        self.drain('R-04', 15)
        self.assertEqual(self.post('/api/robots/R-01/charge', {})[0], 200)
        status, data = self.post('/api/robots/R-04/charge', {})
        self.assertEqual(status, 409)
        self.assertEqual(data['error'], 'all_chargers_busy')

    def test_explicit_busy_charger_is_refused_not_silently_reassigned(self):
        self.add('C1')
        self.add('C2')
        self.drain('R-01', 15)
        self.drain('R-04', 15)
        self.post('/api/robots/R-01/charge', {'charger': 'C1'})
        status, data = self.post('/api/robots/R-04/charge', {'charger': 'C1'})
        self.assertEqual(status, 409)
        self.assertEqual(data['error'], 'charger_unavailable')

    def test_robot_leaving_the_bay_frees_the_charger(self):
        self.add('C1')
        self.drain('R-01', 15)
        self.post('/api/robots/R-01/charge', {})
        self.drain('R-01', 90)  # reports waiting again, i.e. it left the bay
        _, listing = self.get('/api/chargers')
        self.assertEqual(listing['occupancies'], [])
        self.drain('R-04', 15)
        self.assertEqual(self.post('/api/robots/R-04/charge', {})[0], 200)

    def test_vda_state_that_is_not_charging_also_frees_the_bay(self):
        self.add('C1')
        self.drain('R-01', 15)
        self.post('/api/robots/R-01/charge', {})
        self.post('/api/integrations/vda5050', {
            'agv_id': 'R-01', 'message_type': 'state',
            'payload': {'batteryState': {'batteryCharge': 90},
                        'agvPosition': {'x': 10, 'y': 10, 'positionInitialized': True},
                        'orderId': '', 'safetyState': {'eStop': 'NONE'}},
        })
        _, listing = self.get('/api/chargers')
        self.assertEqual(listing['occupancies'], [])

    def test_unknown_robot_and_no_chargers_are_reported(self):
        self.assertEqual(self.get('/api/robots/NOPE/charge')[0], 404)
        self.assertEqual(self.post('/api/robots/NOPE/charge', {})[0], 404)
        self.drain('R-01', 10)
        status, data = self.post('/api/robots/R-01/charge', {})
        self.assertEqual(status, 409)
        self.assertEqual(data['error'], 'no_chargers_configured')

    def test_low_battery_alert_says_whether_charging_is_achievable(self):
        self.drain('R-01', 15)
        _, alerts = self.get('/api/alerts')
        alert = next(a for a in alerts['alerts'] if a['type'] == 'low_battery' and a['robot'] == 'R-01')
        self.assertFalse(alert['charging_available'])
        self.assertIsNone(alert['charger'])

        self.add('C1')
        _, alerts = self.get('/api/alerts')
        alert = next(a for a in alerts['alerts'] if a['type'] == 'low_battery' and a['robot'] == 'R-01')
        self.assertTrue(alert['charging_available'])
        self.assertEqual(alert['charger'], 'C1')


class ChargeQueueTests(OperationsFixture):
    def setUp(self):
        super().setUp()
        self.post('/api/chargers', {'id': 'C1', 'name': 'Bay 1'})

    def drain(self, robot_id, battery):
        self.post('/api/telemetry', {'id': robot_id, 'status': 'waiting', 'battery': battery, 'position': {'x': 10, 'y': 10}})

    def test_refused_robot_is_remembered_in_the_queue(self):
        self.drain('R-01', 15)
        self.post('/api/robots/R-01/charge', {})
        self.drain('R-04', 12)
        status, data = self.post('/api/robots/R-04/charge', {})
        self.assertEqual(status, 409)
        self.assertTrue(data['queued'])

        _, listing = self.get('/api/chargers')
        self.assertEqual([entry['robot_id'] for entry in listing['waiting']], ['R-04'])
        self.assertEqual(listing['admit_now'], [])

    def test_admitted_robot_is_offered_the_freed_bay(self):
        self.drain('R-01', 15)
        self.post('/api/robots/R-01/charge', {})
        self.drain('R-04', 12)
        self.post('/api/robots/R-04/charge', {})
        # R-01 leaves the bay, freeing it; the waiter is offered the bay now.
        self.drain('R-01', 90)
        _, listing = self.get('/api/chargers')
        self.assertEqual(listing['admit_now'], ['R-04'])
        # Once admitted it is no longer "still waiting".
        self.assertEqual(listing['waiting'], [])

        self.assertEqual(self.post('/api/robots/R-04/charge', {})[0], 200)
        _, listing = self.get('/api/chargers')
        self.assertEqual(listing['waiting'], [])
        self.assertEqual(listing['admit_now'], [])

    def test_lowest_battery_waiter_is_admitted_first(self):
        self.drain('R-01', 15)
        self.post('/api/robots/R-01/charge', {})
        self.drain('R-04', 18)
        self.post('/api/robots/R-04/charge', {})
        self.drain('R-07', 8)
        self.post('/api/robots/R-07/charge', {})
        self.drain('R-01', 90)  # bay free
        _, listing = self.get('/api/chargers')
        self.assertEqual(listing['admit_now'], ['R-07'])

    def test_robot_that_no_longer_needs_charge_is_dequeued(self):
        self.drain('R-01', 15)
        self.post('/api/robots/R-01/charge', {})
        self.drain('R-04', 12)
        self.post('/api/robots/R-04/charge', {})
        # R-04 gets topped up elsewhere before it ever reaches a bay.
        self.drain('R-04', 95)
        self.post('/api/robots/R-04/charge', {})
        _, listing = self.get('/api/chargers')
        self.assertEqual(listing['waiting'], [])

    def test_stuck_queue_entry_raises_an_alert(self):
        self.drain('R-01', 15)
        self.post('/api/robots/R-01/charge', {})
        self.drain('R-04', 9)
        self.post('/api/robots/R-04/charge', {})
        # Pretend R-04 has been waiting well past the starvation limit.
        with sqlite3.connect(server.DB_PATH) as db:
            db.execute("UPDATE charger_queue SET requested_at = ? WHERE robot_id = 'R-04'", (time.time() - 1200,))
        _, alerts = self.get('/api/alerts')
        stuck = [a for a in alerts['alerts'] if a['type'] == 'charger_queue_stuck']
        self.assertEqual([a['robot'] for a in stuck], ['R-04'])
        self.assertEqual(stuck[0]['reason'], 'starving')

    def test_critical_waiter_escalates_immediately(self):
        self.drain('R-01', 15)
        self.post('/api/robots/R-01/charge', {})
        self.drain('R-04', 3)
        self.post('/api/robots/R-04/charge', {})
        _, alerts = self.get('/api/alerts')
        stuck = [a for a in alerts['alerts'] if a['type'] == 'charger_queue_stuck']
        self.assertEqual(stuck[0]['reason'], 'critical')
        self.assertEqual(stuck[0]['severity'], 'critical')

    def test_queue_endpoint_orders_waiting_missions(self):
        for priority, deadline in (('low', None), ('urgent', None), ('high', '2026-11-30')):
            self.assertEqual(self.post('/api/missions', {'origin': 'A', 'destination': 'B', 'priority': priority, 'deadline': deadline})[0], 201)
        status, data = self.get('/api/missions/queue')
        self.assertEqual(status, 200)
        priorities = [item['priority'] for item in data['queue']]
        self.assertLess(priorities.index('urgent'), priorities.index('high'))
        self.assertLess(priorities.index('high'), priorities.index('low'))
        self.assertTrue(all(item['status'] == 'waiting' for item in data['queue']))

    def test_complete_frees_robot_and_writes_audit(self):
        self.assertEqual(self.post('/api/missions', {'origin': 'A', 'destination': 'B'})[0], 201)
        created = self.get('/api/missions/queue')[1]['queue'][0]['id']
        number = created.replace('M-', '')
        status, assigned = self.post(f'/api/missions/{number}/assign', {'robot': 'R-04', 'actor': 'supervisor'})
        self.assertEqual(status, 200)
        self.assertEqual(assigned['mission']['progress'], 25)
        status, done = self.post(f'/api/missions/{number}/complete', {'actor': 'supervisor'})
        self.assertEqual(status, 200)
        self.assertEqual(done['mission']['status'], 'done')
        self.assertEqual(done['mission']['progress'], 100)
        _, robots = self.get('/api/robots')
        self.assertEqual({row['id']: row['status'] for row in robots['robots']}['R-04'], 'waiting')
        _, audit = self.get('/api/audit?limit=5')
        actions = [entry['action'] for entry in audit['entries']]
        self.assertEqual(actions[0], 'mission.complete')
        self.assertIn('mission.assign', actions)
        by_action = {entry['action']: entry['actor'] for entry in audit['entries']}
        self.assertEqual(by_action['mission.complete'], 'supervisor')
        self.assertEqual(by_action['mission.assign'], 'supervisor')

    def test_complete_rejects_non_running_mission(self):
        status, _ = self.post('/api/missions/2046/complete', {})
        self.assertEqual(status, 409)

    def test_zone_rule_enforces_routing_and_validates_speed(self):
        for node in (('Z1', 'zone'), ('S1', 'station'), ('S2', 'station')):
            self.assertEqual(self.post('/api/map/nodes', {'id': node[0], 'kind': node[1], 'name': node[0]})[0], 201)
        for edge in ({'source': 'S1', 'target': 'Z1'}, {'source': 'Z1', 'target': 'S2'}):
            self.assertEqual(self.post('/api/map/edges', edge)[0], 201)
        self.assertEqual(self.post('/api/map/route', {'start': 'S1', 'goal': 'S2'})[0], 200)
        self.assertEqual(self.post('/api/map/rules', {'node_id': 'Z1', 'max_speed': 101})[0], 422)
        status, rule = self.post('/api/map/rules', {'node_id': 'Z1', 'max_speed': 40, 'restricted': True, 'actor': 'supervisor'})
        self.assertEqual(status, 200)
        self.assertTrue(rule['routing_enforced'])
        self.assertFalse(rule['speed_enforced'])
        self.assertEqual(self.post('/api/map/route', {'start': 'S1', 'goal': 'S2'})[0], 409)
        _, audit = self.get('/api/audit?limit=1')
        self.assertEqual(audit['entries'][0]['action'], 'zone.rule')

    def test_analytics_and_audit_validate_parameters(self):
        self.assertEqual(self.post('/api/telemetry', {'id': 'R-07', 'status': 'moving', 'battery': 60, 'position': {'x': 20, 'y': 30}})[0], 200)
        status, data = self.get('/api/analytics?days=7')
        self.assertEqual(status, 200)
        self.assertEqual(data['days'], 7)
        self.assertEqual(len(data['telemetry']['daily']), 1)
        self.assertIn('definitions', data)
        for path in ('/api/analytics?days=0', '/api/analytics?days=abc', '/api/audit?limit=0', '/api/audit?limit=501'):
            self.assertEqual(self.get(path)[0], 422, path)


if __name__ == '__main__':
    unittest.main()

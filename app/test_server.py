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


if __name__ == '__main__':
    unittest.main()

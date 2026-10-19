import concurrent.futures
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

import server


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.original_path = server.DB_PATH
        server.DB_PATH = Path(self.temp.name) / 'test.sqlite3'
        server.initialize_db()
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

    def create(self, number=0):
        return self.post('/api/missions', {'origin': f'Origin {number}', 'destination': 'Destination'})

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


if __name__ == '__main__':
    unittest.main()

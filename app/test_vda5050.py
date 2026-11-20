import unittest

import vda5050


def state(**overrides):
    base = {
        'orderId': '',
        'orderUpdateId': 0,
        'lastNodeSequenceId': 0,
        'nodeStates': [],
        'edgeStates': [],
        'actionStates': [],
        'batteryState': {'batteryCharge': 80.4},
        'agvPosition': {'x': 10.0, 'y': 20.0, 'positionInitialized': True},
        'operatingMode': 'AUTOMATIC',
        'safetyState': {'eStop': 'NONE', 'fieldViolation': False},
        'errors': [],
    }
    base.update(overrides)
    return base


class StateConversionTests(unittest.TestCase):
    def test_idle_vehicle_is_waiting_and_coordinates_scale_to_grid(self):
        telemetry = vda5050.state_to_telemetry(state(), map_extent=100)
        self.assertEqual(telemetry['status'], 'waiting')
        self.assertEqual(telemetry['battery'], 80)
        self.assertEqual(telemetry['position'], {'x': 10, 'y': 20})

    def test_open_order_means_moving(self):
        telemetry = vda5050.state_to_telemetry(state(orderId='order-1'))
        self.assertEqual(telemetry['status'], 'moving')
        self.assertEqual(telemetry['order_id'], 'order-1')

    def test_finished_order_is_not_moving(self):
        finished = state(
            orderId='order-1',
            lastNodeSequenceId=2,
            nodeStates=[{'nodeId': 'A', 'sequenceId': 0}, {'nodeId': 'B', 'sequenceId': 2}],
            edgeStates=[{'edgeId': 'A->B', 'sequenceId': 1, 'released': True}],
        )
        self.assertEqual(vda5050.state_to_telemetry(finished)['status'], 'waiting')

    def test_charging_requires_an_active_charging_action(self):
        running = state(actionStates=[{'actionType': 'startCharging', 'actionStatus': 'RUNNING'}])
        self.assertEqual(vda5050.state_to_telemetry(running)['status'], 'charging')
        paused = state(actionStates=[{'actionType': 'startCharging', 'actionStatus': 'PAUSED'}])
        self.assertEqual(vda5050.state_to_telemetry(paused)['status'], 'charging')
        finished = state(actionStates=[{'actionType': 'startCharging', 'actionStatus': 'FINISHED'}])
        self.assertEqual(vda5050.state_to_telemetry(finished)['status'], 'waiting')
        other = state(actionStates=[{'actionType': 'pick', 'actionStatus': 'RUNNING'}])
        self.assertEqual(vda5050.state_to_telemetry(other)['status'], 'waiting')

    def test_coordinates_outside_the_map_are_clamped(self):
        far = state(agvPosition={'x': 250.0, 'y': -40.0, 'positionInitialized': True})
        self.assertEqual(vda5050.state_to_telemetry(far, map_extent=100)['position'], {'x': 100, 'y': 0})

    def test_map_extent_changes_the_scale(self):
        telemetry = vda5050.state_to_telemetry(state(), map_extent=50)
        self.assertEqual(telemetry['position'], {'x': 20, 'y': 40})

    def test_safety_flags_are_surfaced(self):
        unsafe = state(safetyState={'eStop': 'REMOTE', 'fieldViolation': True})
        telemetry = vda5050.state_to_telemetry(unsafe)
        self.assertEqual(telemetry['e_stop'], 'REMOTE')
        self.assertTrue(telemetry['field_violation'])
        self.assertEqual(telemetry['error_count'], 0)

    def test_unknown_e_stop_value_falls_back_to_none(self):
        telemetry = vda5050.state_to_telemetry(state(safetyState={'eStop': 'SOMETHING'}))
        self.assertEqual(telemetry['e_stop'], 'NONE')

    def test_unusable_messages_are_rejected(self):
        cases = {
            'not a dict': 'nope',
            'no battery': state(batteryState=None),
            'battery out of range': state(batteryState={'batteryCharge': 140}),
            'boolean battery': state(batteryState={'batteryCharge': True}),
            'missing position': state(agvPosition=None),
            'non numeric position': state(agvPosition={'x': 'a', 'y': 2}),
            'infinite coordinate': state(agvPosition={'x': float('inf'), 'y': 2}),
        }
        for name, payload in cases.items():
            with self.subTest(name=name):
                self.assertIsNone(vda5050.state_to_telemetry(payload))

    def test_invalid_map_extent_is_rejected(self):
        for extent in (0, -1, '100', None, True):
            with self.subTest(extent=extent):
                self.assertIsNone(vda5050.state_to_telemetry(state(), map_extent=extent))


class ConnectionTests(unittest.TestCase):
    def test_online_and_offline_states(self):
        self.assertTrue(vda5050.connection_is_online({'connectionState': 'ONLINE'}))
        self.assertFalse(vda5050.connection_is_online({'connectionState': 'OFFLINE'}))
        self.assertFalse(vda5050.connection_is_online({'connectionState': 'CONNECTIONBROKEN'}))

    def test_unrecognised_connection_is_unknown(self):
        for payload in ({'connectionState': 'MAYBE'}, {}, None, 'ONLINE'):
            with self.subTest(payload=payload):
                self.assertIsNone(vda5050.connection_is_online(payload))


class OrderMessageTests(unittest.TestCase):
    def test_order_has_nodes_and_edges_in_sequence(self):
        order = vda5050.order_message('order-1', ['A', 'B', 'C'])
        self.assertEqual([node['nodeId'] for node in order['nodes']], ['A', 'B', 'C'])
        self.assertEqual([node['sequenceId'] for node in order['nodes']], [0, 1, 2])
        self.assertEqual([edge['sequenceId'] for edge in order['edges']], [0, 1])
        self.assertTrue(all(node['released'] for node in order['nodes']))

    def test_invalid_orders_are_rejected(self):
        for order_id, path in (('', ['A']), ('order-1', []), ('order-1', ['A', 'A']), ('order-1', ['A', '  '])):
            with self.subTest(order_id=order_id, path=path):
                self.assertIsNone(vda5050.order_message(order_id, path))


if __name__ == '__main__':
    unittest.main()

import unittest

from navigation import reserve_conflicts, shortest_path


class NavigationTests(unittest.TestCase):
    def test_shortest_path_avoids_temporary_obstacle(self):
        edges = [('A', 'B'), ('B', 'C'), ('A', 'D'), ('D', 'C')]
        self.assertEqual(shortest_path(edges, 'A', 'C', blocked={'B'}), ['A', 'D', 'C'])

    def test_unreachable_route_is_empty(self):
        self.assertEqual(shortest_path([('A', 'B')], 'A', 'C'), [])

    def test_conflicts_are_reserved(self):
        self.assertEqual(reserve_conflicts([['A', 'B'], ['C', 'D']]), {'A', 'B', 'C', 'D'})


if __name__ == '__main__':
    unittest.main()

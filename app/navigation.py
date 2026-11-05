from __future__ import annotations

from collections import defaultdict, deque
from typing import Hashable, Iterable

Node = Hashable


def shortest_path(edges: Iterable[tuple[Node, Node]], start: Node, goal: Node, blocked: Iterable[Node] = ()) -> list[Node]:
    blocked_nodes = set(blocked) - {start, goal}
    graph: dict[Node, set[Node]] = defaultdict(set)
    for left, right in edges:
        if left not in blocked_nodes and right not in blocked_nodes:
            graph[left].add(right)
            graph[right].add(left)
    if start == goal:
        return [start]
    queue = deque([start])
    previous: dict[Node, Node | None] = {start: None}
    while queue:
        current = queue.popleft()
        for neighbor in sorted(graph[current], key=str):
            if neighbor in previous:
                continue
            previous[neighbor] = current
            if neighbor == goal:
                path = [goal]
                while previous[path[-1]] is not None:
                    path.append(previous[path[-1]])
                return list(reversed(path))
            queue.append(neighbor)
    return []


def reserve_conflicts(paths: Iterable[Iterable[Node]]) -> set[Node]:
    reserved: set[Node] = set()
    for path in paths:
        reserved.update(path)
    return reserved

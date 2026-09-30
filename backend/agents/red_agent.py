"""Deterministic Red Probe attacker."""

from __future__ import annotations

from typing import Any

try:
    from ..database import get_graph
except ImportError:
    from database import get_graph


PATH_QUERY = (
    "MATCH p = shortestPath((src:Node {type: 'Internet'})-"
    "[*]->(dst:Node {type: 'Database'})) "
    "WHERE all(r IN relationships(p) WHERE r.status = 'ACTIVE') "
    "RETURN [n IN nodes(p) | n.id] AS path_nodes"
)
ACTIVE_PATH_FALLBACK_QUERY = (
    "MATCH p = (src:Node {type: 'Internet'})-[:CONNECTS_TO*]->"
    "(dst:Node {type: 'Database'}) "
    "WHERE all(r IN relationships(p) WHERE r.status = 'ACTIVE') "
    "WITH p, length(p) AS path_length "
    "ORDER BY path_length LIMIT 1 "
    "RETURN [n IN nodes(p) | n.id] AS path_nodes"
)


class RedAgent:
    """Simulate an attacker moving toward the database crown jewel."""

    def __init__(self, graph: Any | None = None) -> None:
        self.graph = graph or get_graph()

    @staticmethod
    def _rows(result: Any) -> list[list[Any]]:
        return list(getattr(result, "result_set", result or []))

    def step(self, graph: Any | None = None) -> str:
        """Compromise the first healthy node on the shortest active path."""
        active_graph = graph or self.graph
        try:
            result = active_graph.query(PATH_QUERY)
        except Exception:
            result = active_graph.query(ACTIVE_PATH_FALLBACK_QUERY)
        rows = self._rows(result)
        if not rows:
            result = active_graph.query(ACTIVE_PATH_FALLBACK_QUERY)
            rows = self._rows(result)
        if not rows or not rows[0][0]:
            return "Attack blocked: No route to crown jewel"

        path_nodes = list(rows[0][0])
        status_result = active_graph.query(
            "MATCH (n:Node) WHERE n.id IN $node_ids "
            "RETURN n.id, n.status ORDER BY n.id",
            {"node_ids": path_nodes},
        )
        statuses = {row[0]: row[1] for row in self._rows(status_result)}
        target_id = next(
            (node_id for node_id in path_nodes[1:] if statuses.get(node_id) != "COMPROMISED"),
            None,
        )
        if target_id is None:
            return "Attack blocked: No route to crown jewel"

        active_graph.query(
            "MATCH (n:Node {id: $node_id}) SET n.status = 'COMPROMISED'",
            {"node_id": target_id},
        )
        return "Red Probe breached node: %s" % target_id

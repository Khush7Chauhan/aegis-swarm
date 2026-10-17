"""Deterministic Red Probe attacker.

Traversal is restricted to ``CONNECTS_TO`` relationships and to edges whose
status is ``ACTIVE``. It never traverses ``GENERATED`` (the audit edge to
IncidentReports) or any other relationship type.

Query strategy:
1. ``SHORTEST_PATH_QUERY`` — the required ``shortestPath`` query. FalkorDB
   requires ``shortestPath`` to appear in a ``WITH``/``RETURN`` clause, so it is
   projected in ``WITH``.
2. ``ACTIVE_PATH_FALLBACK_QUERY`` — a documented compatibility fallback used
   when FalkorDB rejects the ``shortestPath`` syntax *or* the shortest hop-path
   contains a non-``ACTIVE`` edge. It selects the shortest path whose
   relationships are all ``ACTIVE``.
"""

from __future__ import annotations

from typing import Any

try:
    from ..database import get_graph
except ImportError:
    from database import get_graph


SHORTEST_PATH_QUERY = (
    "MATCH (src:Node {type: 'Internet'}), (dst:Node {type: 'Database'}) "
    "WITH shortestPath((src)-[:CONNECTS_TO*]->(dst)) AS path "
    "WHERE path IS NOT NULL "
    "AND all(rel IN relationships(path) WHERE rel.status = 'ACTIVE') "
    "RETURN [n IN nodes(path) | n.id] AS path_nodes"
)

ACTIVE_PATH_FALLBACK_QUERY = (
    "MATCH path = (src:Node {type: 'Internet'})-[:CONNECTS_TO*]->(dst:Node {type: 'Database'}) "
    "WHERE all(rel IN relationships(path) WHERE rel.status = 'ACTIVE') "
    "WITH path, length(path) AS path_length "
    "ORDER BY path_length LIMIT 1 "
    "RETURN [n IN nodes(path) | n.id] AS path_nodes"
)

STATUS_QUERY = (
    "MATCH (n:Node) WHERE n.id IN $node_ids "
    "RETURN n.id, n.status ORDER BY n.id"
)

COMPROMISE_QUERY = "MATCH (n:Node {id: $node_id}) SET n.status = 'COMPROMISED'"


class RedAgent:
    """Simulate an attacker moving toward the database crown jewel."""

    def __init__(self, graph: Any | None = None) -> None:
        self.graph = graph or get_graph()

    @staticmethod
    def _rows(result: Any) -> list[list[Any]]:
        return list(getattr(result, "result_set", result or []))

    @staticmethod
    def _active_path(graph: Any) -> list[str] | None:
        """Return the shortest all-ACTIVE Internet->Database path, or None."""
        rows: list[list[Any]] = []
        try:
            rows = RedAgent._rows(graph.query(SHORTEST_PATH_QUERY))
        except Exception:
            rows = []
        if not rows:
            rows = RedAgent._rows(graph.query(ACTIVE_PATH_FALLBACK_QUERY))
        if rows and rows[0][0]:
            return list(rows[0][0])
        return None

    def step(self, graph: Any | None = None) -> str:
        """Compromise the first healthy node on the shortest active path."""
        active_graph = graph or self.graph
        path_nodes = self._active_path(active_graph)
        if not path_nodes:
            return "Attack blocked: No route to crown jewel"

        status_rows = self._rows(
            active_graph.query(STATUS_QUERY, {"node_ids": path_nodes})
        )
        statuses = {row[0]: row[1] for row in status_rows}
        target_id = next(
            (node_id for node_id in path_nodes[1:] if statuses.get(node_id) != "COMPROMISED"),
            None,
        )
        if target_id is None:
            return "Attack blocked: No route to crown jewel"

        active_graph.query(COMPROMISE_QUERY, {"node_id": target_id})
        return "Red Probe breached node: %s" % target_id

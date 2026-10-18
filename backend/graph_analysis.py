"""Graph-native analysis helpers shared by the agents, the API, and the evaluation.

Everything here is read-only except ``refresh_metrics`` which writes derived,
graph-computed analytics back onto nodes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _rows(result: Any) -> list[list[Any]]:
    return list(getattr(result, "result_set", result or []))


# --------------------------------------------------------------------------- #
# Reachability: status-aware, restricted to CONNECTS_TO relationships only.
# Severed edges (and any non-ACTIVE edge) can never contribute to reachability.
# --------------------------------------------------------------------------- #
DATABASE_REACHABILITY_QUERY = (
    "MATCH p = (node:Node {id: $node_id})-[:CONNECTS_TO*]->(database:Node {type: 'Database'}) "
    "WHERE all(rel IN relationships(p) WHERE rel.status = 'ACTIVE') "
    "RETURN count(p) > 0 AS reachable"
)
ANY_ENTRY_REACHABILITY_QUERY = (
    "MATCH p = (entry:Node {type: 'Internet'})-[:CONNECTS_TO*]->(database:Node {type: 'Database'}) "
    "WHERE all(rel IN relationships(p) WHERE rel.status = 'ACTIVE') "
    "RETURN count(p) > 0 AS reachable"
)


def database_reachable(graph: Any, node_id: str) -> bool:
    """True only when an all-ACTIVE CONNECTS_TO path leads to a Database node."""
    rows = _rows(graph.query(DATABASE_REACHABILITY_QUERY, {"node_id": node_id}))
    return bool(rows and rows[0][0])


def database_reachability_remaining(graph: Any) -> bool:
    """True when any attacker entry point can still reach a Database over ACTIVE edges."""
    rows = _rows(graph.query(ANY_ENTRY_REACHABILITY_QUERY))
    return bool(rows and rows[0][0])


DATABASE_STATUS_QUERY = "MATCH (n:Node {type: 'Database'}) RETURN n.status"


def database_compromised(graph: Any) -> bool:
    """True when the crown-jewel Database node has been breached by Red."""
    rows = _rows(graph.query(DATABASE_STATUS_QUERY))
    return any(row[0] == "COMPROMISED" for row in rows)


# --------------------------------------------------------------------------- #
# Audit / reporting queries
# --------------------------------------------------------------------------- #
COMPROMISED_QUERY = "MATCH (n:Node {status: 'COMPROMISED'}) RETURN n.id ORDER BY n.id"
SEVERED_QUERY = (
    "MATCH (source:Node)-[edge:CONNECTS_TO]->(target:Node) "
    "WHERE edge.status = 'SEVERED' "
    "RETURN source.id, target.id, edge.severed_by, edge.sever_reason, edge.severed_at "
    "ORDER BY source.id, target.id"
)
INCIDENT_REPORTS_QUERY = (
    "MATCH (report:IncidentReport) "
    "RETURN report.timestamp, report.source, report.target, report.severity, report.reasoning "
    "ORDER BY report.timestamp DESC"
)
INCIDENT_COUNT_QUERY = "MATCH (report:IncidentReport) RETURN count(report)"


def compromised_node_ids(graph: Any) -> list[str]:
    return [row[0] for row in _rows(graph.query(COMPROMISED_QUERY))]


def severed_edges(graph: Any) -> list[dict[str, Any]]:
    """Return the durable sever audit trail kept in FalkorDB."""
    return [
        {
            "source": row[0],
            "target": row[1],
            "severed_by": row[2],
            "sever_reason": row[3],
            "severed_at": row[4],
        }
        for row in _rows(graph.query(SEVERED_QUERY))
    ]


def incident_reports(graph: Any) -> list[dict[str, Any]]:
    return [
        {"timestamp": row[0], "source": row[1], "target": row[2], "severity": row[3], "reasoning": row[4]}
        for row in _rows(graph.query(INCIDENT_REPORTS_QUERY))
    ]


def incident_report_count(graph: Any) -> int:
    rows = _rows(graph.query(INCIDENT_COUNT_QUERY))
    return int(rows[0][0]) if rows else 0


# --------------------------------------------------------------------------- #
# Metrics: computed from the live graph where FalkorDB supports it.
# --------------------------------------------------------------------------- #
PAGERANK_QUERY = "CALL algo.pageRank('Node', 'CONNECTS_TO') YIELD node, score RETURN node.id, score"
DEGREE_QUERY = (
    "MATCH (n:Node) OPTIONAL MATCH (n)-[rel:CONNECTS_TO]-(neighbour:Node) "
    "RETURN n.id AS id, count(rel) AS degree ORDER BY id"
)


def refresh_metrics(graph: Any) -> dict[str, Any]:
    """Recompute PageRank (FalkorDB algo) and degree centrality from the live graph.

    Falls back to the seeded baseline per-metric if a computation is unavailable,
    and reports exactly which source each metric came from.
    """
    errors: list[str] = []
    pagerank_source = "seed"

    try:
        rows = _rows(graph.query(PAGERANK_QUERY))
        if rows:
            for node_id, score in rows:
                graph.query(
                    "MATCH (n:Node {id: $id}) SET n.pagerank = $score, n.pagerank_source = 'computed'",
                    {"id": node_id, "score": float(score)},
                )
            pagerank_source = "computed"
    except Exception as exc:  # pragma: no cover - depends on FalkorDB build
        errors.append("pageRank: %s" % exc)

    centrality_source = "seed"
    try:
        degrees = {row[0]: int(row[1]) for row in _rows(graph.query(DEGREE_QUERY))}
        max_degree = max(degrees.values()) if degrees else 0
        for node_id, degree in degrees.items():
            graph.query(
                "MATCH (n:Node {id: $id}) SET n.centrality = $value, n.centrality_source = 'computed'",
                {"id": node_id, "value": (degree / max_degree) if max_degree else 0.0},
            )
        centrality_source = "computed"
    except Exception as exc:  # pragma: no cover - depends on FalkorDB build
        errors.append("degreeCentrality: %s" % exc)

    return {
        "pagerank_source": pagerank_source,
        "centrality_source": centrality_source,
        "centrality_definition": "normalized degree centrality over CONNECTS_TO edges",
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "errors": errors,
    }

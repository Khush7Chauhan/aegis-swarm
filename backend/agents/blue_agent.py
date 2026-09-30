"""Blue sentinel: isolates the most valuable active outbound chokepoint."""

from typing import Any


class BlueAgent:
    """Defender that severs an exposed route from a compromised node."""

    def defend(self, graph: Any) -> dict[str, Any]:
        """Find and sever the highest-value active edge leaving a compromised node."""
        result = graph.query(
            "MATCH (source:Node {status: 'COMPROMISED'})-[:CONNECTS_TO]->"
            "(target:Node) "
            "WHERE target.type = 'Database' OR target.centrality >= 0.8 "
            "MATCH (source)-[edge:CONNECTS_TO]->(target) "
            "WHERE edge.status IN ['ACTIVE', 'ATTACK_VECTOR'] "
            "RETURN source.id, source.name, target.id, target.name, id(edge) "
            "ORDER BY target.centrality DESC LIMIT 1"
        )
        rows = getattr(result, "result_set", result or [])
        if not rows:
            return {
                "agent": "BLUE",
                "type": "INFO",
                "message": "Sentinel sweep complete: No exposed chokepoint detected",
                "severed": None,
            }

        source_id, source_name, target_id, target_name, edge_id = rows[0]
        graph.query(
            "MATCH ()-[edge:CONNECTS_TO]->() WHERE id(edge) = $edge_id "
            "SET edge.status = 'SEVERED'",
            {"edge_id": edge_id},
        )
        return {
            "agent": "BLUE",
            "type": "MITIGATION",
            "message": "Chokepoint identified at %s. Edge severed to protect %s" % (source_name, target_name),
            "severed": {"source": source_id, "target": target_id, "edge_id": edge_id},
        }

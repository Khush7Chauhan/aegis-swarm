"""Red adversary: advances one hop along the shortest active attack path."""

from typing import Any


PATH_QUERY = (
    "MATCH (src:Node {type: 'Internet'}), (dst:Node {type: 'Database'}) "
    "WITH shortestPath((src)-[:CONNECTS_TO*]->(dst)) AS p "
    "WHERE p IS NOT NULL AND all(r IN relationships(p) WHERE r.status = 'ACTIVE') "
    "RETURN [n in nodes(p) | n.id] AS path, "
    "[r in relationships(p) | id(r)] AS rel_ids"
)


class RedAgent:
    """Attacker that compromises the next healthy node on the active route."""

    def step(self, graph: Any) -> dict[str, Any]:
        """Compromise one node and mark its incoming edge as an attack vector."""
        result = graph.query(PATH_QUERY)
        rows = getattr(result, "result_set", result or [])
        if not rows:
            return {
                "agent": "RED",
                "type": "BLOCKED",
                "message": "Attack blocked: No route to crown jewel",
                "path": [],
            }

        path = list(rows[0][0] or [])
        rel_ids = list(rows[0][1] or [])
        if len(path) < 2:
            return {
                "agent": "RED",
                "type": "BLOCKED",
                "message": "Attack blocked: No route to crown jewel",
                "path": path,
            }

        node_rows = graph.query(
            "MATCH (n:Node) WHERE n.id IN $path RETURN n.id, n.name, n.status",
            {"path": path},
        )
        node_status = {
            row[0]: {"name": row[1], "status": row[2]}
            for row in getattr(node_rows, "result_set", node_rows or [])
        }
        next_index = next(
            (index for index, node_id in enumerate(path[1:], 1)
             if node_status.get(node_id, {}).get("status") != "COMPROMISED"),
            None,
        )
        if next_index is None:
            return {
                "agent": "RED",
                "type": "BLOCKED",
                "message": "Attack blocked: No route to crown jewel",
                "path": path,
            }

        target_id = path[next_index]
        target = node_status.get(target_id, {})
        graph.query(
            "MATCH (n:Node {id: $id}) SET n.status = 'COMPROMISED'",
            {"id": target_id},
        )
        if next_index - 1 < len(rel_ids):
            graph.query(
                "MATCH ()-[r:CONNECTS_TO]->() WHERE id(r) = $rel_id "
                "SET r.status = 'ATTACK_VECTOR'",
                {"rel_id": rel_ids[next_index - 1]},
            )

        name = target.get("name", target_id)
        return {
            "agent": "RED",
            "type": "BREACH",
            "message": "Target acquired: %s breached" % name,
            "path": path,
            "target": target_id,
        }

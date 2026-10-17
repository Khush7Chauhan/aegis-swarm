"""Seed the Aegis enterprise network topology in FalkorDB.

The ``centrality`` and ``pagerank`` values written here are a **seeded
architectural-risk baseline** (hand-tuned for the five-node demo topology), not
live analytics. They are tagged ``*_source: 'seed'`` and are overwritten by
``graph_analysis.refresh_metrics()`` on reset/startup with values actually
computed from the live graph whenever FalkorDB exposes the required algorithm.
"""

from database import execute_query


def seed_database() -> None:
    """Replace the Aegis graph with the baseline five-node topology."""
    execute_query("MATCH (n) DETACH DELETE n")

    # (id, name, type, centrality, pagerank) -- see module docstring re: seeding.
    nodes = [
        ("gw-1", "PUBLIC-GW", "Internet", 0.12, 0.04),
        ("web-1", "WEB-AUTH-01", "Gateway", 0.68, 0.22),
        ("api-billing", "BILLING-SVC", "Microservice", 0.89, 0.45),
        ("api-users", "USER-PROFILE", "Microservice", 0.35, 0.15),
        ("db-core", "CORE-DB-PROD", "Database", 0.95, 0.88),
    ]
    for node_id, name, node_type, centrality, pagerank in nodes:
        execute_query(
            "CREATE (n:Node {id: $id, name: $name, type: $type, status: 'HEALTHY', "
            "centrality: $centrality, pagerank: $pagerank, "
            "centrality_source: 'seed', pagerank_source: 'seed'})",
            {
                "id": node_id,
                "name": name,
                "type": node_type,
                "centrality": centrality,
                "pagerank": pagerank,
            },
        )

    relationships = [
        ("gw-1", "web-1"),
        ("web-1", "api-billing"),
        ("web-1", "api-users"),
        ("api-billing", "db-core"),
        ("api-users", "db-core"),
    ]
    for source, target in relationships:
        execute_query(
            "MATCH (source:Node {id: $source}), (target:Node {id: $target}) "
            "CREATE (source)-[:CONNECTS_TO {status: 'ACTIVE'}]->(target)",
            {"source": source, "target": target},
        )


if __name__ == "__main__":
    seed_database()

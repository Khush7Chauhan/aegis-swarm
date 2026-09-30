"""Shared FalkorDB connection and Cypher execution helpers."""

import logging
from typing import Any

from falkordb import FalkorDB

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

db = FalkorDB(host="localhost", port=6379)


def get_graph() -> Any:
    """Return the shared Aegis graph handle."""
    return db.select_graph("aegis")


def execute_query(cypher: str, params: dict | None = None) -> Any:
    """Execute Cypher against the Aegis graph and surface connection failures."""
    try:
        logger.info("Executing Cypher: %s", cypher)
        return get_graph().query(cypher, params or {})
    except Exception:
        logger.exception("FalkorDB query failed")
        raise

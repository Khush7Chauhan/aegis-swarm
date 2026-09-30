"""FastAPI command API for the Aegis Swarm simulation."""

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    from .agents.blue_agent import BlueAgent
    from .agents.red_agent import RedAgent
    from .database import get_graph
    from .seeder import seed_database
except ImportError:
    from agents.blue_agent import BlueAgent
    from agents.red_agent import RedAgent
    from database import get_graph
    from seeder import seed_database


app = FastAPI(title="Aegis Swarm API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

feed_events: list[dict[str, Any]] = []
red_agent = RedAgent()
blue_agent = BlueAgent()


def _query_rows(graph: Any, cypher: str) -> list[list[Any]]:
    result = graph.query(cypher)
    return list(getattr(result, "result_set", result or []))


def _event(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": result.get("agent", "SYSTEM"),
        "message": result["message"],
        "type": result.get("type", "INFO"),
    }


def _service_call(operation):
    try:
        return operation()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="FalkorDB operation failed: %s" % exc) from exc


@app.get("/api/graph")
def graph_state() -> dict[str, list[dict[str, Any]]]:
    def read_graph() -> dict[str, list[dict[str, Any]]]:
        graph = get_graph()
        node_rows = _query_rows(
            graph,
            "MATCH (n:Node) RETURN n.id, n.name, n.type, n.status, "
            "n.centrality, n.pagerank",
        )
        edge_rows = _query_rows(
            graph,
            "MATCH (source:Node)-[edge:CONNECTS_TO]->(target:Node) "
            "RETURN source.id, target.id, edge.status",
        )
        return {
            "nodes": [
                {
                    "id": row[0],
                    "name": row[1],
                    "type": row[2],
                    "status": row[3],
                    "centrality": float(row[4]),
                    "pagerank": float(row[5]),
                }
                for row in node_rows
            ],
            "edges": [
                {"source": row[0], "target": row[1], "status": row[2]}
                for row in edge_rows
            ],
        }

    return _service_call(read_graph)


@app.post("/api/red/step")
def red_step() -> dict[str, Any]:
    result = _service_call(lambda: red_agent.step(get_graph()))
    feed_events.append(_event(result))
    return result


@app.post("/api/blue/defend")
def blue_defend() -> dict[str, Any]:
    result = _service_call(lambda: blue_agent.defend(get_graph()))
    feed_events.append(_event(result))
    return result


@app.post("/api/reset")
def reset() -> dict[str, str]:
    def reset_graph() -> dict[str, str]:
        seed_database()
        feed_events.clear()
        event = _event({"agent": "SYSTEM", "type": "RESET", "message": "Baseline topology restored"})
        feed_events.append(event)
        return {"status": "ok", "message": event["message"]}

    return _service_call(reset_graph)


@app.get("/api/feed")
def feed() -> list[dict[str, Any]]:
    return feed_events

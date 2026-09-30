"""FastAPI API for the Aegis Swarm tactical console."""

from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    from .agents.blue_agent import BlueAgent
    from .agents.red_agent import RedAgent
    from .database import get_graph
except ImportError:
    from agents.blue_agent import BlueAgent
    from agents.red_agent import RedAgent
    from database import get_graph


app = FastAPI(title="Aegis Swarm API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

feed_events: list[dict[str, str]] = []
graph = get_graph()
red_agent = RedAgent(graph)
blue_agent = BlueAgent(graph)


def _rows(result: Any) -> list[list[Any]]:
    return list(getattr(result, "result_set", result or []))


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Aegis backend operation failed: %s" % exc) from exc


def _append_event(agent: str, message: str, event_type: str) -> dict[str, str]:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "message": message,
        "type": event_type,
    }
    feed_events.append(event)
    return event


@app.post("/api/red/step")
def red_step() -> dict[str, str]:
    message = _run(red_agent.step)
    event = _append_event("RED", message, "BREACH" if "breached" in message else "BLOCKED")
    return {"status": "ok", "message": event["message"]}


@app.post("/api/blue/defend")
def blue_defend() -> dict[str, str]:
    message = _run(blue_agent.defend)
    event = _append_event("BLUE", message, "MITIGATION" if message != "idle" else "INFO")
    return {"status": "ok", "message": event["message"]}


@app.get("/api/feed")
def feed() -> list[dict[str, str]]:
    return feed_events


@app.get("/api/graph")
def graph_state() -> dict[str, list[dict[str, Any]]]:
    def read_graph() -> dict[str, list[dict[str, Any]]]:
        node_rows = _rows(graph.query(
            "MATCH (n:Node) RETURN n.id, n.name, n.type, n.status, "
            "n.centrality, n.pagerank"
        ))
        edge_rows = _rows(graph.query(
            "MATCH (source:Node)-[edge:CONNECTS_TO]->(target:Node) "
            "RETURN source.id, target.id, edge.status"
        ))
        return {
            "nodes": [
                {
                    "id": row[0],
                    "name": row[1],
                    "type": row[2],
                    "status": row[3],
                    "centrality": float(row[4] or 0),
                    "pagerank": float(row[5] or 0),
                }
                for row in node_rows
            ],
            "edges": [
                {"source": row[0], "target": row[1], "status": row[2]}
                for row in edge_rows
            ],
        }

    return _run(read_graph)

"""FastAPI API for the Aegis Swarm tactical console."""

from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    from .agents.blue_agent import BlueAgent
    from .agents.red_agent import RedAgent
    from .database import get_graph
    from .evaluation import run_evaluation
    from .graph_analysis import refresh_metrics
    from .seeder import seed_database
except ImportError:
    from agents.blue_agent import BlueAgent
    from agents.red_agent import RedAgent
    from database import get_graph
    from evaluation import run_evaluation
    from graph_analysis import refresh_metrics
    from seeder import seed_database


app = FastAPI(title="Aegis Swarm API", version="1.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

feed_events: list[dict[str, Any]] = []
graph = get_graph()
red_agent = RedAgent(graph)
blue_agent = BlueAgent(graph)
metrics_state: dict[str, Any] = {}


def _rows(result: Any) -> list[list[Any]]:
    return list(getattr(result, "result_set", result or []))


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Aegis backend operation failed: %s" % exc) from exc


def _append_event(agent: str, message: str, event_type: str, **extra: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "message": message,
        "type": event_type,
    }
    # Preserve reasoning / action / decision_source separately from the summary.
    event.update({key: value for key, value in extra.items() if value is not None})
    feed_events.append(event)
    return event


def _reset_graph() -> dict[str, Any]:
    """Restore the baseline topology, clear the feed, and refresh live metrics."""
    seed_database()
    feed_events.clear()
    metrics_state.clear()
    metrics_state.update(refresh_metrics(graph))
    return metrics_state


# Establish a measured, clean baseline when the API boots.
try:
    _reset_graph()
except Exception as exc:  # pragma: no cover - defensive; DB may be offline at import
    feed_events.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": "SYSTEM",
            "message": "Startup baseline refresh failed: %s" % exc,
            "type": "WARNING",
        }
    )


@app.post("/api/red/step")
def red_step() -> dict[str, Any]:
    message = _run(red_agent.step)
    event_type = "BREACH" if "breached" in message else "BLOCKED"
    _append_event("RED", message, event_type)
    return {"status": "ok", "message": message}


@app.post("/api/blue/defend")
def blue_defend() -> dict[str, Any]:
    action = _run(blue_agent.defend)
    message = action.get("message") or "idle"
    decision_source = action.get("decision_source", "none")
    if not action.get("severed"):
        event_type = "INFO"
    elif decision_source == "fallback":
        event_type = "FALLBACK"
    else:
        event_type = "MITIGATION"
    _append_event(
        "BLUE",
        message,
        event_type,
        reasoning=action.get("reasoning"),
        decision_source=decision_source,
        action=action.get("action"),
        llm_error=action.get("llm_error"),
    )
    return {"status": "ok", "message": message, "action": action}


@app.get("/api/feed")
def feed() -> list[dict[str, Any]]:
    return feed_events


@app.post("/api/reset")
def reset() -> dict[str, Any]:
    def reset_graph() -> dict[str, Any]:
        metrics = _reset_graph()
        message = "Baseline topology restored"
        _append_event("SYSTEM", message, "RESET")
        return {"status": "ok", "message": message, "metrics": metrics}

    return _run(reset_graph)


@app.post("/api/metrics/refresh")
def metrics_refresh() -> dict[str, Any]:
    def do_refresh() -> dict[str, Any]:
        metrics_state.clear()
        metrics_state.update(refresh_metrics(graph))
        return {"status": "ok", "metrics": metrics_state}

    return _run(do_refresh)


@app.post("/api/eval/scenario")
def eval_scenario() -> dict[str, Any]:
    """Run the reproducible Red-vs-Blue scenario and return auditable evidence."""

    def scenario() -> dict[str, Any]:
        evaluation = run_evaluation(lambda: _reset_graph(), red_agent, blue_agent, graph)
        return {"status": "ok", "evaluation": evaluation}

    return _run(scenario)


@app.get("/api/graph")
def graph_state() -> dict[str, Any]:
    def read_graph() -> dict[str, Any]:
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
            "metrics": metrics_state,
        }

    return _run(read_graph)

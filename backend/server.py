"""FastAPI API for the Aegis Swarm tactical console."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

try:
    from .agents.blue_agent import BlueAgent
    from .agents.red_agent import RedAgent
    from .database import get_graph
    from .evaluation import run_evaluation
    from .graph_analysis import database_compromised, database_reachability_remaining, refresh_metrics
    from .seeder import seed_database
except ImportError:
    from agents.blue_agent import BlueAgent
    from agents.red_agent import RedAgent
    from database import get_graph
    from evaluation import run_evaluation
    from graph_analysis import database_compromised, database_reachability_remaining, refresh_metrics
    from seeder import seed_database


app = FastAPI(title="Aegis Swarm API", version="1.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

RED_INTERVAL_SECONDS = 2.0
BLUE_INTERVAL_SECONDS = 2.5

feed_events: list[dict[str, Any]] = []
graph = get_graph()
red_agent = RedAgent(graph)
blue_agent = BlueAgent(graph)
metrics_state: dict[str, Any] = {}

simulation_state: dict[str, Any] = {"running": False, "status": "IDLE"}
simulation_task: "asyncio.Task[None] | None" = None


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
    event.update({key: value for key, value in extra.items() if value is not None})
    feed_events.append(event)
    return event


def _record_red(message: str) -> str:
    """Normalise a Red step into a feed event and return its event type."""
    event_type = "BREACH" if "breached" in message else "BLOCKED"
    _append_event("RED", message, event_type)
    return event_type


def _record_blue(action: dict[str, Any]) -> dict[str, Any]:
    """Normalise a Blue defense action into a feed event."""
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
    return action


def _reset_graph() -> dict[str, Any]:
    """Restore the baseline topology, clear the feed, and refresh live metrics."""
    seed_database()
    feed_events.clear()
    metrics_state.clear()
    metrics_state.update(refresh_metrics(graph))
    return metrics_state


try:
    _reset_graph()
except Exception as exc:
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
    _record_red(message)
    return {"status": "ok", "message": message}


@app.post("/api/blue/defend")
def blue_defend() -> dict[str, Any]:
    action = _run(blue_agent.defend)
    _record_blue(action)
    return {"status": "ok", "message": action.get("message") or "idle", "action": action}


@app.get("/api/feed")
def feed() -> list[dict[str, Any]]:
    return feed_events


@app.post("/api/reset")
async def reset() -> dict[str, Any]:
    global simulation_task

    if simulation_task and not simulation_task.done():
        simulation_task.cancel()
        try:
            await simulation_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    simulation_task = None
    _set_simulation_state(running=False, status="IDLE")

    def reset_graph() -> dict[str, Any]:
        metrics = _reset_graph()
        message = "Baseline topology restored"
        _append_event("SYSTEM", message, "RESET")
        return {"status": "ok", "message": message, "metrics": metrics, "sim_status": "IDLE"}

    return await asyncio.to_thread(_run, reset_graph)


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
def graph_state(include_memory: bool = Query(default=False)) -> dict[str, Any]:
    def read_graph() -> dict[str, Any]:
        node_rows = _rows(graph.query(
            "MATCH (n:Node) RETURN n.id, n.name, n.type, n.status, "
            "n.centrality, n.pagerank"
        ))
        edge_rows = _rows(graph.query(
            "MATCH (source:Node)-[edge:CONNECTS_TO]->(target:Node) "
            "RETURN source.id, target.id, edge.status"
        ))
        nodes: list[dict[str, Any]] = [
            {
                "id": row[0],
                "name": row[1],
                "type": row[2],
                "status": row[3],
                "centrality": float(row[4] or 0),
                "pagerank": float(row[5] or 0),
            }
            for row in node_rows
        ]
        edges: list[dict[str, Any]] = [
            {"source": row[0], "target": row[1], "status": row[2]}
            for row in edge_rows
        ]

        if include_memory:
            memory_rows = _rows(graph.query(
                "MATCH (src:Node)-[r:GENERATED]->(m:IncidentReport) "
                "RETURN m.id, m.agent, m.reasoning, m.severity, m.timestamp, src.id"
            ))
            for index, row in enumerate(memory_rows):
                raw_id, agent, reasoning, severity, timestamp, source_id = row
                memory_id = raw_id or "IR-%s-%s" % (source_id, timestamp or index)
                nodes.append(
                    {
                        "id": memory_id,
                        "name": memory_id,
                        "type": "IncidentReport",
                        "status": severity or "HIGH",
                        "agent": agent or "Blue Sentinel",
                        "reasoning": reasoning,
                        "severity": severity or "HIGH",
                        "timestamp": timestamp,
                        "centrality": 0.0,
                        "pagerank": 0.0,
                    }
                )
                edges.append(
                    {
                        "source": source_id,
                        "target": memory_id,
                        "status": "MEMORY_LINK",
                    }
                )

        return {"nodes": nodes, "edges": edges, "metrics": metrics_state}

    return _run(read_graph)


def _set_simulation_state(*, running: bool, status: str) -> None:
    simulation_state["running"] = running
    simulation_state["status"] = status


def _breach_check() -> bool:
    """True when Red has breached the crown-jewel database."""
    return database_compromised(graph)


def _containment_check() -> bool:
    """True when Blue has severed every ACTIVE route to the database."""
    return not database_reachability_remaining(graph)


async def simulation_loop() -> None:
    """Hands-free Red/Blue loop until breach, containment, or cancellation.

    Blocking FalkorDB work is dispatched with ``asyncio.to_thread`` (the modern
    equivalent of Starlette's ``run_in_threadpool``) so the FastAPI event loop
    is never blocked. Two agent cadences run as sibling tasks and share a stop
    event; cancelling this supervisor cancels both. Cancellation is treated as
    an expected shutdown path, never as a server error.
    """
    stop_event = asyncio.Event()

    async def red_loop() -> None:
        while not stop_event.is_set():
            await asyncio.sleep(RED_INTERVAL_SECONDS)
            if stop_event.is_set():
                return
            try:
                message = await asyncio.to_thread(red_agent.step)
                _record_red(message)
                breached = await asyncio.to_thread(_breach_check)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _append_event("SYSTEM", "Red agent fault: %s" % exc, "WARNING")
                stop_event.set()
                return
            if breached:
                _append_event(
                    "SYSTEM",
                    "Red breached the crown-jewel database. Autonomous loop halted.",
                    "BREACH",
                )
                _set_simulation_state(running=False, status="BREACHED")
                stop_event.set()
                return

    async def blue_loop() -> None:
        while not stop_event.is_set():
            await asyncio.sleep(BLUE_INTERVAL_SECONDS)
            if stop_event.is_set():
                return
            try:
                action = await asyncio.to_thread(blue_agent.defend)
                _record_blue(action)
                contained = await asyncio.to_thread(_containment_check)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _append_event("SYSTEM", "Blue agent fault: %s" % exc, "WARNING")
                stop_event.set()
                return
            if contained:
                _append_event(
                    "SYSTEM",
                    "Blue severed all ACTIVE routes to the database. Threat contained.",
                    "CONTAINED",
                )
                _set_simulation_state(running=False, status="CONTAINED")
                stop_event.set()
                return

    workers = [asyncio.create_task(red_loop()), asyncio.create_task(blue_loop())]
    try:
        await asyncio.gather(*workers)
    except asyncio.CancelledError:
        stop_event.set()
        raise
    finally:
        stop_event.set()
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)


@app.post("/api/simulation/start")
async def simulation_start() -> dict[str, Any]:
    global simulation_task

    if simulation_task and not simulation_task.done():
        _set_simulation_state(running=True, status="ACTIVE")
        return {
            "status": "ok",
            "running": True,
            "sim_status": "ACTIVE",
            "message": "Autonomous Stigmergy Engaged",
        }

    try:
        if await asyncio.to_thread(database_compromised, graph):
            _set_simulation_state(running=False, status="BREACHED")
            _append_event("SYSTEM", "Database already breached; reset before engaging.", "WARNING")
            return {"status": "ok", "running": False, "sim_status": "BREACHED", "message": "Database already breached"}
        if not await asyncio.to_thread(database_reachability_remaining, graph):
            _set_simulation_state(running=False, status="CONTAINED")
            _append_event("SYSTEM", "All routes already severed; reset before engaging.", "WARNING")
            return {"status": "ok", "running": False, "sim_status": "CONTAINED", "message": "Threat already contained"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Aegis backend operation failed: %s" % exc) from exc

    _set_simulation_state(running=True, status="ACTIVE")
    _append_event("SYSTEM", "Autonomous stigmergy engaged.", "ACTIVE")
    simulation_task = asyncio.create_task(simulation_loop())
    return {
        "status": "ok",
        "running": True,
        "sim_status": "ACTIVE",
        "message": "Autonomous Stigmergy Engaged",
    }


@app.post("/api/simulation/stop")
async def simulation_stop() -> dict[str, Any]:
    global simulation_task

    if simulation_task and not simulation_task.done():
        simulation_task.cancel()
        try:
            await simulation_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    simulation_task = None
    _set_simulation_state(running=False, status="IDLE")
    _append_event("SYSTEM", "Autonomous stigmergy disengaged.", "IDLE")
    return {"status": "ok", "running": False, "sim_status": "IDLE", "message": "Swarm Halted"}


@app.get("/api/simulation/status")
def simulation_status() -> dict[str, Any]:
    running = bool(simulation_task and not simulation_task.done())
    if not running and simulation_state["status"] == "ACTIVE":
        _set_simulation_state(running=False, status="IDLE")
    return {"running": running, "status": simulation_state["status"]}

"""Tests for the autonomous warfare loop and the forensic memory graph endpoint.

These use a small in-memory fake graph and stub agents so no FalkorDB or OpenAI
connection is required beyond importing ``server`` (which connects at import,
matching the rest of the suite's assumptions).
"""

from __future__ import annotations

import asyncio

import pytest

import server


class FakeResult:
    def __init__(self, result_set):
        self.result_set = result_set


class SimGraph:
    """Minimal graph supporting exactly the queries used by ``server``."""

    def __init__(self):
        self.db_status = "HEALTHY"
        self.routes = True

    def query(self, cypher, params=None):
        c = " ".join(cypher.split())
        if "type: 'Database'" in c and "RETURN n.status" in c:
            return FakeResult([[self.db_status]])
        if "count(p) > 0" in c:
            return FakeResult([[self.routes]])
        if "MATCH (n:Node) RETURN n.id" in c:
            return FakeResult([["db-core", "CORE-DB-PROD", "Database", self.db_status, 0.95, 0.88]])
        if "CONNECTS_TO]->(target:Node) RETURN source.id" in c:
            return FakeResult([["api-billing", "db-core", "ACTIVE"]])
        if "GENERATED]->(m:IncidentReport)" in c:
            return FakeResult([["IR-abc123", "Blue Sentinel", "cut the chokepoint", "HIGH", 111, "api-billing"]])
        raise AssertionError("SimGraph received an unexpected query: %s" % c)


class BreachingRed:
    def __init__(self, graph):
        self.graph = graph

    def step(self):
        self.graph.db_status = "COMPROMISED"
        return "Red Probe breached node: db-core"


class SeveringBlue:
    def __init__(self, graph):
        self.graph = graph

    def defend(self):
        self.graph.routes = False
        return {"message": "Blue severed the route", "severed": True, "decision_source": "openai", "reasoning": "r"}


@pytest.fixture
def sim(monkeypatch):
    graph = SimGraph()
    monkeypatch.setattr(server, "graph", graph)
    monkeypatch.setattr(server, "red_agent", BreachingRed(graph))
    monkeypatch.setattr(server, "blue_agent", SeveringBlue(graph))
    monkeypatch.setattr(server, "RED_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(server, "BLUE_INTERVAL_SECONDS", 0.03)
    monkeypatch.setattr(server, "simulation_task", None)
    server.feed_events.clear()
    server._set_simulation_state(running=False, status="IDLE")
    yield graph
    # Never leak a running task into the next test.
    task = server.simulation_task
    if task and not task.done():
        task.cancel()
    server.simulation_task = None
    server._set_simulation_state(running=False, status="IDLE")


def test_breach_auto_stops_loop(sim):
    async def scenario():
        start = await server.simulation_start()
        assert start["running"] is True and start["sim_status"] == "ACTIVE"
        await asyncio.sleep(0.12)

    asyncio.run(scenario())
    status = server.simulation_status()
    assert status["running"] is False
    assert status["status"] == "BREACHED"
    assert any(event["type"] == "BREACH" for event in server.feed_events)


def test_containment_auto_stops_loop(monkeypatch, sim):
    class SafeRed:
        def __init__(self, graph):
            self.graph = graph

        def step(self):
            return "Red Probe breached node: web-1"

    monkeypatch.setattr(server, "red_agent", SafeRed(sim))

    async def scenario():
        await server.simulation_start()
        await asyncio.sleep(0.16)

    asyncio.run(scenario())
    status = server.simulation_status()
    assert status["running"] is False
    assert status["status"] == "CONTAINED"


def test_manual_stop_returns_idle(monkeypatch, sim):
    class IdleRed:
        def __init__(self, graph):
            self.graph = graph

        def step(self):
            return "Red Probe breached node: web-1"

    class IdleBlue:
        def __init__(self, graph):
            self.graph = graph

        def defend(self):
            return {"message": "idle", "severed": False, "decision_source": "none", "reasoning": ""}

    monkeypatch.setattr(server, "red_agent", IdleRed(sim))
    monkeypatch.setattr(server, "blue_agent", IdleBlue(sim))

    async def scenario():
        await server.simulation_start()
        await asyncio.sleep(0.05)
        assert server.simulation_status()["running"] is True
        stop = await server.simulation_stop()
        assert stop["running"] is False and stop["sim_status"] == "IDLE"

    asyncio.run(scenario())
    assert server.simulation_status()["status"] == "IDLE"


def test_start_is_idempotent_while_running(monkeypatch, sim):
    class IdleRed:
        def __init__(self, graph):
            self.graph = graph

        def step(self):
            return "Red Probe breached node: web-1"

    class IdleBlue:
        def __init__(self, graph):
            self.graph = graph

        def defend(self):
            return {"message": "idle", "severed": False, "decision_source": "none", "reasoning": ""}

    monkeypatch.setattr(server, "red_agent", IdleRed(sim))
    monkeypatch.setattr(server, "blue_agent", IdleBlue(sim))

    async def scenario():
        first = await server.simulation_start()
        second = await server.simulation_start()
        assert first["running"] and second["running"]
        await server.simulation_stop()

    asyncio.run(scenario())


def test_graph_memory_nodes_only_when_requested(sim):
    plain = server.graph_state(include_memory=False)
    assert all(node["type"] != "IncidentReport" for node in plain["nodes"])
    assert all(edge["status"] != "MEMORY_LINK" for edge in plain["edges"])

    with_memory = server.graph_state(include_memory=True)
    memory_nodes = [node for node in with_memory["nodes"] if node["type"] == "IncidentReport"]
    memory_edges = [edge for edge in with_memory["edges"] if edge["status"] == "MEMORY_LINK"]

    assert len(memory_nodes) == 1
    assert memory_nodes[0]["name"] == "IR-abc123"
    assert memory_nodes[0]["reasoning"] == "cut the chokepoint"
    assert memory_edges == [{"source": "api-billing", "target": "IR-abc123", "status": "MEMORY_LINK"}]

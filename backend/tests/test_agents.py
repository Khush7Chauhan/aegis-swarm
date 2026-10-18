"""Agent tests using a fake graph and fake OpenAI clients (no DB, no network).

Covers: Red route selection + documented fallback, Blue observation, invalid
LLM selection rejection, valid LLM mutation, IncidentReport write/reuse,
status-aware reachability, and clearly-marked fallback behaviour.
"""

from __future__ import annotations

import json
from collections import deque
from types import SimpleNamespace

import pytest

from agents.blue_agent import BlueAgent
from agents.red_agent import RedAgent
from evaluation import run_evaluation
from graph_analysis import database_reachable, database_reachability_remaining


class FakeResult:
    def __init__(self, result_set):
        self.result_set = result_set


class FakeGraph:
    """In-memory stand-in for a FalkorDB graph supporting the queries the agents use."""

    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.incidents = []
        self.reject_shortest_path = False
        self.queries = []

    def add_node(self, node_id, name, node_type, status="HEALTHY", centrality=0.0, pagerank=0.0):
        self.nodes[node_id] = {
            "id": node_id, "name": name, "type": node_type, "status": status,
            "centrality": centrality, "pagerank": pagerank,
        }

    def add_edge(self, source, target, status="ACTIVE"):
        self.edges[(source, target)] = {"status": status}

    def _active_shortest_path(self):
        starts = [nid for nid, node in self.nodes.items() if node["type"] == "Internet"]
        goals = {nid for nid, node in self.nodes.items() if node["type"] == "Database"}
        best = None
        for start in starts:
            queue = deque([[start]])
            visited = {start}
            while queue:
                path = queue.popleft()
                node = path[-1]
                if node in goals and len(path) > 1:
                    if best is None or len(path) < len(best):
                        best = path
                    break
                for (source, target), edge in self.edges.items():
                    if source == node and edge["status"] == "ACTIVE" and target not in visited:
                        visited.add(target)
                        queue.append(path + [target])
        return best

    def _reaches_database(self, node_id):
        goals = {nid for nid, node in self.nodes.items() if node["type"] == "Database"}
        queue = deque([node_id])
        visited = {node_id}
        while queue:
            current = queue.popleft()
            if current in goals and current != node_id:
                return True
            for (source, target), edge in self.edges.items():
                if source == current and edge["status"] == "ACTIVE" and target not in visited:
                    visited.add(target)
                    queue.append(target)
        return False

    def query(self, cypher, params=None):
        params = params or {}
        c = " ".join(cypher.split())
        self.queries.append(c)

        if "algo.pageRank" in c:
            return FakeResult([])
        if "shortestPath" in c:
            if self.reject_shortest_path:
                raise Exception(
                    "FalkorDB currently only supports shortestPaths in WITH or RETURN clauses"
                )
            path = self._active_shortest_path()
            return FakeResult([[path]] if path else [])
        if "ORDER BY path_length" in c:
            path = self._active_shortest_path()
            return FakeResult([[path]] if path else [])
        if "SET n.status = 'COMPROMISED'" in c:
            self.nodes[params["node_id"]]["status"] = "COMPROMISED"
            return FakeResult([])
        if "RETURN n.id, n.status ORDER BY n.id" in c:
            ids = params.get("node_ids", [])
            return FakeResult([[nid, self.nodes[nid]["status"]] for nid in sorted(ids) if nid in self.nodes])
        if "RETURN source.id, source.name, target.id" in c:
            rows = []
            for (source, target), edge in sorted(self.edges.items()):
                if self.nodes[source]["status"] == "COMPROMISED" and edge["status"] in ("ACTIVE", "ATTACK_VECTOR"):
                    rows.append([
                        source, self.nodes[source]["name"], target, self.nodes[target]["name"],
                        self.nodes[target]["type"], self.nodes[target]["centrality"],
                        self.nodes[target]["pagerank"], hash((source, target)), edge["status"],
                    ])
            return FakeResult(rows)
        if "WHERE edge.status = 'SEVERED'" in c and "edge.severed_by" in c:
            rows = []
            for order, ((source, target), edge) in enumerate(sorted(self.edges.items())):
                if edge["status"] == "SEVERED":
                    rows.append([source, target, edge.get("severed_by"), edge.get("sever_reason"), order])
            return FakeResult(rows)
        if "source.status = 'COMPROMISED'" in c and "RETURN source.id, target.id" in c:
            source, target = params["source"], params["target"]
            edge = self.edges.get((source, target))
            ok = (
                edge is not None
                and self.nodes.get(source, {}).get("status") == "COMPROMISED"
                and edge["status"] in ("ACTIVE", "ATTACK_VECTOR")
            )
            return FakeResult([[source, target]] if ok else [])
        if "RETURN report.timestamp, report.reasoning, report.severity" in c:
            return FakeResult([[r["timestamp"], r["reasoning"], r["severity"]] for r in reversed(self.incidents)])
        if "report.source, report.target" in c:
            return FakeResult([
                [r["timestamp"], r["source"], r["target"], r["severity"], r["reasoning"]]
                for r in reversed(self.incidents)
            ])
        if "count(report)" in c:
            return FakeResult([[len(self.incidents)]])
        if "count(p) > 0" in c:
            node_id = params.get("node_id")
            reachable = self._active_shortest_path() is not None if node_id is None else self._reaches_database(node_id)
            return FakeResult([[reachable]])
        if "SET edge.status = 'SEVERED'" in c:
            key = (params["source"], params["target"])
            self.edges[key]["status"] = "SEVERED"
            self.edges[key]["severed_by"] = "Blue Sentinel"
            self.edges[key]["sever_reason"] = params["reason"]
            return FakeResult([])
        if "CREATE (source)-[:GENERATED]" in c:
            self.incidents.append({
                "timestamp": len(self.incidents) + 1,
                "source": params["source"],
                "target": params["target"],
                "severity": "HIGH",
                "reasoning": params["reason"],
            })
            return FakeResult([])
        if "MATCH (n:Node {status: 'COMPROMISED'}) RETURN n.id ORDER BY n.id" in c:
            return FakeResult([[nid] for nid in sorted(self.nodes) if self.nodes[nid]["status"] == "COMPROMISED"])
        if "OPTIONAL MATCH (n)-[rel:CONNECTS_TO]" in c:
            rows = [
                [nid, sum(1 for (s, t) in self.edges if s == nid or t == nid)]
                for nid in sorted(self.nodes)
            ]
            return FakeResult(rows)
        raise AssertionError("FakeGraph received an unexpected query: %s" % c)


NODES = [
    ("gw-1", "PUBLIC-GW", "Internet", 0.12, 0.04),
    ("web-1", "WEB-AUTH-01", "Gateway", 0.68, 0.22),
    ("api-billing", "BILLING-SVC", "Microservice", 0.89, 0.45),
    ("api-users", "USER-PROFILE", "Microservice", 0.35, 0.15),
    ("db-core", "CORE-DB-PROD", "Database", 0.95, 0.88),
]
EDGES = [
    ("gw-1", "web-1"),
    ("web-1", "api-billing"),
    ("web-1", "api-users"),
    ("api-billing", "db-core"),
    ("api-users", "db-core"),
]


def seed_fake(graph):
    graph.nodes.clear()
    graph.edges.clear()
    graph.incidents.clear()
    for node_id, name, node_type, centrality, pagerank in NODES:
        graph.add_node(node_id, name, node_type, centrality=centrality, pagerank=pagerank)
    for source, target in EDGES:
        graph.add_edge(source, target)


def build_graph():
    graph = FakeGraph()
    seed_fake(graph)
    return graph


class FakeCompletions:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.completions = FakeCompletions(response=response, error=error)
        self.chat = SimpleNamespace(completions=self.completions)


def tool_response(name, arguments):
    function = SimpleNamespace(name=name, arguments=arguments)
    message = SimpleNamespace(tool_calls=[SimpleNamespace(function=function)])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture(autouse=True)
def _no_live_openai(monkeypatch):
    """Guarantee tests never make a real OpenAI request."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_red_selects_first_downstream_uncompromised_node():
    graph = build_graph()
    red = RedAgent(graph)

    message = red.step()

    assert message == "Red Probe breached node: web-1"
    assert graph.nodes["web-1"]["status"] == "COMPROMISED"
    assert graph.nodes["gw-1"]["status"] == "HEALTHY"


def test_red_uses_documented_fallback_when_shortestpath_rejected():
    graph = build_graph()
    graph.reject_shortest_path = True
    red = RedAgent(graph)

    message = red.step()

    assert "breached node: web-1" in message
    assert any("shortestPath" in q for q in graph.queries), "must attempt shortestPath first"
    assert any("ORDER BY path_length" in q for q in graph.queries), "must fall back to shortest ACTIVE path"


def test_red_blocked_when_all_active_paths_severed():
    graph = build_graph()
    graph.edges[("web-1", "api-billing")]["status"] = "SEVERED"
    graph.edges[("web-1", "api-users")]["status"] = "SEVERED"

    assert RedAgent(graph).step() == "Attack blocked: No route to crown jewel"


def test_blue_observes_real_candidates():
    graph = build_graph()
    graph.nodes["web-1"]["status"] = "COMPROMISED"

    observation = BlueAgent(graph, client=FakeClient())._observation()

    pairs = {(c["compromised_node"], c["target_downstream_node"]) for c in observation["candidates"]}
    assert pairs == {("web-1", "api-billing"), ("web-1", "api-users")}
    assert all(c["can_reach_database"] is True for c in observation["candidates"])


def test_severed_edges_excluded_from_active_reachability():
    graph = build_graph()
    graph.nodes["web-1"]["status"] = "COMPROMISED"
    assert database_reachable(graph, "web-1") is True

    graph.edges[("web-1", "api-billing")]["status"] = "SEVERED"
    graph.edges[("web-1", "api-users")]["status"] = "SEVERED"

    assert database_reachable(graph, "web-1") is False
    assert database_reachability_remaining(graph) is False


def test_valid_llm_selection_is_mutated():
    graph = build_graph()
    graph.nodes["web-1"]["status"] = "COMPROMISED"
    selection = {"compromised_node": "web-1", "target_downstream_node": "api-billing", "ai_reasoning": "chokepoint"}
    blue = BlueAgent(graph, client=FakeClient(tool_response("isolate_threat", json.dumps(selection))))

    result = blue.defend()

    assert result["decision_source"] == "openai"
    assert result["severed"] is True
    assert result["validation_result"]["valid"] is True
    assert result["mutation_result"]["incident_report_created"] is True
    assert graph.edges[("web-1", "api-billing")]["status"] == "SEVERED"
    assert graph.edges[("web-1", "api-billing")]["sever_reason"] == "chokepoint"


def test_invalid_llm_selection_is_rejected_then_falls_back():
    graph = build_graph()
    graph.nodes["web-1"]["status"] = "COMPROMISED"
    selection = {"compromised_node": "gw-1", "target_downstream_node": "db-core", "ai_reasoning": "invented"}
    blue = BlueAgent(graph, client=FakeClient(tool_response("isolate_threat", json.dumps(selection))))

    result = blue.defend()

    assert result["decision_source"] == "fallback"
    assert result["llm_attempted"] is True
    assert result["rejected_selection"]["source"] == "gw-1"
    assert result["rejected_selection"]["validation_result"]["valid"] is False
    assert ("gw-1", "db-core") not in graph.edges
    assert result["severed"] is True


def test_incident_report_written_and_reused_in_next_observation():
    graph = build_graph()
    graph.nodes["web-1"]["status"] = "COMPROMISED"
    selection = {"compromised_node": "web-1", "target_downstream_node": "api-billing", "ai_reasoning": "first cut"}
    client = FakeClient(tool_response("isolate_threat", json.dumps(selection)))
    blue = BlueAgent(graph, client=client)

    blue.defend()

    assert len(graph.incidents) == 1
    observation = blue._observation()
    assert observation["prior_incidents"][0]["reasoning"] == "first cut"
    messages = blue.build_messages(observation)
    assert "first cut" in messages[1]["content"], "prior IncidentReports must be in the prompt"


def test_model_failure_is_marked_fallback_and_error_surfaced():
    graph = build_graph()
    graph.nodes["web-1"]["status"] = "COMPROMISED"
    blue = BlueAgent(graph, client=FakeClient(error=RuntimeError("model offline")))

    result = blue.defend()

    assert result["decision_source"] == "fallback"
    assert result["llm_attempted"] is True
    assert "model offline" in result["llm_error"]


def test_missing_api_key_is_fallback_without_llm_attempt():
    graph = build_graph()
    graph.nodes["web-1"]["status"] = "COMPROMISED"
    blue = BlueAgent(graph, client=None)

    result = blue.defend()

    assert result["decision_source"] == "fallback"
    assert result["llm_attempted"] is False
    assert result["severed"] is True


def test_evaluation_scenario_is_json_serializable_and_correct():
    graph = build_graph()
    red = RedAgent(graph)
    blue = BlueAgent(graph, client=None)

    result = run_evaluation(lambda: seed_fake(graph), red, blue, graph)

    json.dumps(result)
    assert result["decision_source"] == "fallback"
    assert result["blue_actions"] == 1
    assert result["incident_report_count"] == 1
    assert result["severed_edges"], "an edge must be severed"
    assert result["database_reachability_remaining"] is True, "an attack path remains via api-users"
    assert any(step["step"] == "red_attack_2" for step in result["steps"])

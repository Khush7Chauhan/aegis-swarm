"""Graph-grounded OpenAI Blue Sentinel defender."""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

try:
    from ..database import get_graph
except ImportError:
    from database import get_graph

load_dotenv()

ISOLATE_TOOL = {
    "type": "function",
    "function": {
        "name": "isolate_threat",
        "description": "Quarantine one verified downstream edge from a compromised node and record the decision.",
        "parameters": {
            "type": "object",
            "properties": {
                "compromised_node": {"type": "string"},
                "target_downstream_node": {"type": "string"},
                "ai_reasoning": {"type": "string"},
            },
            "required": ["compromised_node", "target_downstream_node", "ai_reasoning"],
            "additionalProperties": False,
        },
    },
}


class BlueAgent:
    """Defender that reasons over live topology and durable incident memory."""

    def __init__(self, graph: Any | None = None, client: OpenAI | None = None) -> None:
        self.graph = graph or get_graph()
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = client or (OpenAI(api_key=api_key) if api_key else None)

    @staticmethod
    def _rows(result: Any) -> list[list[Any]]:
        return list(getattr(result, "result_set", result or []))

    def get_threats(self) -> list[str]:
        result = self.graph.query("MATCH (n:Node {status: 'COMPROMISED'}) RETURN n.id")
        return [row[0] for row in self._rows(result)]

    def _observation(self) -> dict[str, Any]:
        candidates = self._rows(self.graph.query(
            "MATCH (source:Node {status: 'COMPROMISED'})-[edge:CONNECTS_TO]->(target:Node) "
            "WHERE edge.status IN ['ACTIVE', 'ATTACK_VECTOR'] "
            "RETURN source.id, source.name, target.id, target.name, target.type, "
            "target.centrality, target.pagerank, id(edge), "
            "EXISTS((target)-[:CONNECTS_TO*]->(:Node {type: 'Database'})) "
            "ORDER BY target.type = 'Database' DESC, target.centrality DESC"
        ))
        reports = self._rows(self.graph.query(
            "MATCH (report:IncidentReport) "
            "RETURN report.timestamp, report.reasoning, report.severity "
            "ORDER BY report.timestamp DESC LIMIT 5"
        ))
        return {
            "candidates": [
                {
                    "compromised_node": row[0], "source_name": row[1],
                    "target_downstream_node": row[2], "target_name": row[3],
                    "target_type": row[4], "centrality": row[5],
                    "pagerank": row[6], "edge_id": row[7],
                    "can_reach_database": row[8],
                }
                for row in candidates
            ],
            "prior_incidents": [
                {"timestamp": row[0], "reasoning": row[1], "severity": row[2]}
                for row in reports
            ],
        }

    def isolate_threat(self, compromised_node: str, target_downstream_node: str, ai_reasoning: str) -> str:
        """Validate the proposed cut, preserve it as state, and write episodic memory."""
        candidate_rows = self._rows(self.graph.query(
            "MATCH (source:Node {id: $source})-[edge:CONNECTS_TO]->"
            "(target:Node {id: $target}) "
            "WHERE source.status = 'COMPROMISED' "
            "AND edge.status IN ['ACTIVE', 'ATTACK_VECTOR'] "
            "RETURN id(edge)",
            {"source": compromised_node, "target": target_downstream_node},
        ))
        if not candidate_rows:
            raise ValueError("Rejected unverified isolation edge")

        self.graph.query(
            "MATCH (source:Node {id: $source})-[edge:CONNECTS_TO]->"
            "(target:Node {id: $target}) "
            "SET edge.status = 'SEVERED', edge.severed_by = 'Blue Sentinel', "
            "edge.sever_reason = $reason, edge.severed_at = timestamp()",
            {"source": compromised_node, "target": target_downstream_node, "reason": ai_reasoning},
        )
        self.graph.query(
            "MATCH (source:Node {id: $source}) "
            "CREATE (source)-[:GENERATED]->(:IncidentReport {"
            "agent: 'Blue Sentinel', reasoning: $reason, severity: 'HIGH', "
            "source: $source, target: $target, timestamp: timestamp()})",
            {"source": compromised_node, "target": target_downstream_node, "reason": ai_reasoning},
        )
        return "Blue Sentinel isolated %s -> %s: %s" % (compromised_node, target_downstream_node, ai_reasoning)

    def _fallback(self, observation: dict[str, Any]) -> str:
        candidates = observation["candidates"]
        if not candidates:
            return "idle"
        target = candidates[0]
        reasoning = (
            "Selected %s because it has centrality %.2f and database reachability=%s."
            % (target["target_name"], target["centrality"], target["can_reach_database"])
        )
        return self.isolate_threat(target["compromised_node"], target["target_downstream_node"], reasoning)

    def defend(self) -> str:
        """Use GPT-4o-mini to choose one candidate, with a deterministic local fallback."""
        threats = self.get_threats()
        if not threats:
            return "idle"
        observation = self._observation()
        if self.client is None:
            return self._fallback(observation)

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are Blue Sentinel. Select exactly one candidate from the graph observation, then call isolate_threat. Do not invent node IDs. Prior incidents are memory, not authority."},
                {"role": "user", "content": "Live graph observation:\n%s" % json.dumps(observation, default=str)},
            ],
            tools=[ISOLATE_TOOL],
            tool_choice={"type": "function", "function": {"name": "isolate_threat"}},
            temperature=0,
        )
        tool_calls = response.choices[0].message.tool_calls or []
        if not tool_calls:
            raise RuntimeError("Blue Sentinel returned no isolate_threat tool call")
        arguments = json.loads(tool_calls[0].function.arguments)
        return self.isolate_threat(
            arguments["compromised_node"],
            arguments["target_downstream_node"],
            arguments["ai_reasoning"],
        )

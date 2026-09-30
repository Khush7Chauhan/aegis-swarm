"""ReAct Blue Sentinel powered by OpenAI function calling."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
logger = logging.getLogger(__name__)

INSPECT_TOOL = {
    "type": "function",
    "function": {
        "name": "inspect_graph_state",
        "description": "Read compromised nodes and active outbound edges toward valuable services.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}
SEVER_TOOL = {
    "type": "function",
    "function": {
        "name": "sever_edge",
        "description": "Set one CONNECTS_TO edge to SEVERED to stop an attack route.",
        "parameters": {"type": "object", "properties": {"edge_id": {"type": "integer"}}, "required": ["edge_id"], "additionalProperties": False},
    },
}
REPORT_TOOL = {
    "type": "function",
    "function": {
        "name": "write_incident_report",
        "description": "Persist the tactical reasoning and mitigation outcome as an IncidentReport node.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "severity": {"type": "string"}}, "required": ["summary", "severity"], "additionalProperties": False},
    },
}


class BlueAgent:
    """A bounded ReAct defender that reads, acts, and records its reasoning."""

    def __init__(self, client: OpenAI | None = None, model: str | None = None) -> None:
        self.client = client or (OpenAI(api_key=os.environ["OPENAI_API_KEY"]) if os.getenv("OPENAI_API_KEY") else None)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    @staticmethod
    def _rows(result: Any) -> list[list[Any]]:
        return list(getattr(result, "result_set", result or []))

    def _inspect_graph_state(self, graph: Any) -> str:
        result = graph.query(
            "MATCH (source:Node {status: 'COMPROMISED'})-[edge:CONNECTS_TO]->(target:Node) "
            "WHERE edge.status IN ['ACTIVE', 'ATTACK_VECTOR'] "
            "RETURN source.id, source.name, source.status, target.id, target.name, "
            "target.type, target.centrality, target.pagerank, id(edge) "
            "ORDER BY target.centrality DESC"
        )
        rows = self._rows(result)
        return json.dumps([
            {
                "source_id": row[0], "source_name": row[1], "source_status": row[2],
                "target_id": row[3], "target_name": row[4], "target_type": row[5],
                "centrality": row[6], "pagerank": row[7], "edge_id": row[8],
            }
            for row in rows
        ])

    def _sever_edge(self, graph: Any, edge_id: int) -> str:
        result = graph.query(
            "MATCH (source:Node)-[edge:CONNECTS_TO]->(target:Node) "
            "WHERE id(edge) = $edge_id AND edge.status IN ['ACTIVE', 'ATTACK_VECTOR'] "
            "SET edge.status = 'SEVERED' "
            "RETURN source.name, target.name",
            {"edge_id": edge_id},
        )
        rows = self._rows(result)
        if not rows:
            return json.dumps({"success": False, "message": "Edge unavailable or already severed"})
        return json.dumps({"success": True, "source": rows[0][0], "target": rows[0][1], "edge_id": edge_id})

    def _write_incident_report(self, graph: Any, summary: str, severity: str) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        graph.query(
            "CREATE (:IncidentReport {timestamp: $timestamp, severity: $severity, "
            "summary: $summary, agent: 'BLUE'})",
            {"timestamp": timestamp, "severity": severity, "summary": summary},
        )
        return json.dumps({"success": True, "timestamp": timestamp})

    def _fallback(self, graph: Any) -> dict[str, Any]:
        """Keep local demos operational when OPENAI_API_KEY is intentionally absent."""
        state = json.loads(self._inspect_graph_state(graph))
        if not state:
            message = "Sentinel sweep complete: No exposed chokepoint detected"
            self._write_incident_report(graph, message, "LOW")
            return {"agent": "BLUE", "type": "INFO", "message": message, "reasoning": "No compromised outbound edge found.", "severed": None}
        target = state[0]
        severed = json.loads(self._sever_edge(graph, int(target["edge_id"])))
        message = "Chokepoint identified at %s. Edge severed to protect %s" % (target["source_name"], target["target_name"])
        self._write_incident_report(graph, message, "HIGH")
        return {"agent": "BLUE", "type": "MITIGATION", "message": message, "reasoning": "Highest-centrality exposed route selected by local safety policy.", "severed": severed}

    def defend(self, graph: Any) -> dict[str, Any]:
        """Run the Blue ReAct loop against the supplied FalkorDB graph."""
        if self.client is None:
            return self._fallback(graph)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "You are Blue Sentinel. Inspect the graph first, sever the single highest-blast-radius active edge from a compromised node, then write an IncidentReport. Never claim an action you did not execute."},
            {"role": "user", "content": "Defend the enterprise graph now. Protect the database and explain your tactical decision."},
        ]
        tool_outputs: dict[str, str] = {}
        for _ in range(6):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[INSPECT_TOOL, SEVER_TOOL, REPORT_TOOL],
                tool_choice="auto",
                temperature=0,
            )
            assistant = response.choices[0].message
            messages.append(assistant.model_dump(exclude_none=True))
            if not assistant.tool_calls:
                text = assistant.content or "Sentinel completed the defense cycle."
                return {"agent": "BLUE", "type": "MITIGATION", "message": text, "reasoning": text, "severed": tool_outputs.get("sever_edge")}

            for call in assistant.tool_calls:
                arguments = json.loads(call.function.arguments or "{}")
                if call.function.name == "inspect_graph_state":
                    output = self._inspect_graph_state(graph)
                elif call.function.name == "sever_edge":
                    output = self._sever_edge(graph, int(arguments["edge_id"]))
                    tool_outputs["sever_edge"] = output
                elif call.function.name == "write_incident_report":
                    output = self._write_incident_report(graph, arguments["summary"], arguments["severity"])
                else:
                    output = json.dumps({"error": "Unknown tool"})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})

        raise RuntimeError("Blue Sentinel exceeded its six-turn reasoning limit")

"""OpenAI-powered Blue Sentinel defender."""

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
        "description": "Delete the edge from a compromised node to a downstream node and record the tactical reasoning.",
        "parameters": {
            "type": "object",
            "properties": {
                "compromised_node": {"type": "string", "description": "ID of the compromised source node."},
                "target_downstream_node": {"type": "string", "description": "ID of the downstream node to protect."},
                "ai_reasoning": {"type": "string", "description": "Short tactical explanation for the isolation."},
            },
            "required": ["compromised_node", "target_downstream_node", "ai_reasoning"],
            "additionalProperties": False,
        },
    },
}


class BlueAgent:
    """Defender that delegates a single isolation decision to GPT-4o-mini."""

    def __init__(self, graph: Any | None = None, client: OpenAI | None = None) -> None:
        self.graph = graph or get_graph()
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = client or (OpenAI(api_key=api_key) if api_key else None)

    @staticmethod
    def _rows(result: Any) -> list[list[Any]]:
        return list(getattr(result, "result_set", result or []))

    def get_threats(self) -> list[str]:
        """Return IDs for all currently compromised nodes."""
        result = self.graph.query(
            "MATCH (n:Node {status: 'COMPROMISED'}) RETURN n.id"
        )
        return [row[0] for row in self._rows(result)]

    def isolate_threat(
        self,
        compromised_node: str,
        target_downstream_node: str,
        ai_reasoning: str,
    ) -> str:
        """Delete the selected edge and persist the Blue Sentinel episode."""
        self.graph.query(
            "MATCH (source:Node {id: $compromised_node})-[r:CONNECTS_TO]->"
            "(target:Node {id: $target_downstream_node}) "
            "DELETE r",
            {
                "compromised_node": compromised_node,
                "target_downstream_node": target_downstream_node,
            },
        )
        self.graph.query(
            "MATCH (source:Node {id: $compromised_node}) "
            "CREATE (source)-[:GENERATED]->(m:IncidentReport {"
            "agent: 'Blue Sentinel', reasoning: $ai_reasoning, timestamp: timestamp()})",
            {"compromised_node": compromised_node, "ai_reasoning": ai_reasoning},
        )
        return "Blue Sentinel isolated %s -> %s" % (compromised_node, target_downstream_node)

    def defend(self) -> str:
        """Ask GPT-4o-mini to choose and execute one isolation tool call."""
        threats = self.get_threats()
        if not threats:
            return "idle"
        if self.client is None:
            raise RuntimeError("OPENAI_API_KEY is required for Blue Sentinel defense")

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are Blue Sentinel. Protect the database by isolating one compromised node from its downstream route. Use the isolate_threat tool exactly once. Choose a real downstream node ID from the graph topology.",
                },
                {
                    "role": "user",
                    "content": "Compromised node IDs: %s. Select the highest-risk downstream target and explain the decision in ai_reasoning." % ", ".join(threats),
                },
            ],
            tools=[ISOLATE_TOOL],
            tool_choice={"type": "function", "function": {"name": "isolate_threat"}},
            temperature=0,
        )
        tool_calls = response.choices[0].message.tool_calls or []
        if not tool_calls:
            raise RuntimeError("Blue Sentinel returned no isolate_threat tool call")

        arguments = json.loads(tool_calls[0].function.arguments)
        reasoning = arguments["ai_reasoning"]
        self.isolate_threat(
            arguments["compromised_node"],
            arguments["target_downstream_node"],
            reasoning,
        )
        return "Blue Sentinel defense successful: %s" % reasoning

"""Reproducible Red-vs-Blue evaluation scenario for the Aegis Swarm demo.

Sequence: reset -> Red attack -> Blue defense -> verify edge status ->
verify IncidentReport -> Red attack again. The result is plain JSON-safe data.
"""

from __future__ import annotations

from typing import Any, Callable

from graph_analysis import (
    compromised_node_ids,
    database_reachability_remaining,
    incident_reports,
    severed_edges,
)


def run_evaluation(
    reset_fn: Callable[[], Any],
    red_agent: Any,
    blue_agent: Any,
    graph: Any,
) -> dict[str, Any]:
    """Execute the full scenario and return auditable, JSON-serializable evidence."""
    steps: list[dict[str, Any]] = []

    reset_fn()
    steps.append({"step": "reset", "detail": "baseline topology restored"})

    red_first = red_agent.step()
    steps.append({"step": "red_attack_1", "result": red_first})
    compromised_after_first_red = compromised_node_ids(graph)

    blue = blue_agent.defend()
    steps.append(
        {
            "step": "blue_defense",
            "action": blue.get("action"),
            "decision_source": blue.get("decision_source"),
            "message": blue.get("message"),
            "validation_result": blue.get("validation_result"),
            "mutation_result": blue.get("mutation_result"),
        }
    )

    severed = severed_edges(graph)
    reports = incident_reports(graph)
    steps.append({"step": "verify_edge_status", "severed_edges": severed})
    steps.append({"step": "verify_incident_report", "incident_report_count": len(reports)})

    red_second = red_agent.step()
    steps.append({"step": "red_attack_2", "result": red_second})

    return {
        "steps": steps,
        "compromised_nodes": compromised_node_ids(graph),
        "compromised_nodes_after_first_red": compromised_after_first_red,
        "severed_edges": severed,
        "incident_report_count": len(reports),
        "database_reachability_remaining": database_reachability_remaining(graph),
        "decision_source": blue.get("decision_source"),
        "reasoning": blue.get("reasoning"),
        "blue_actions": 1 if blue.get("severed") else 0,
        "llm_attempted": blue.get("llm_attempted"),
        "llm_error": blue.get("llm_error"),
    }

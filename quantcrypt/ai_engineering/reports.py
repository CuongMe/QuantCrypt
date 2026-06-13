from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AgentReport:
    agent_name: str
    output_summary: str
    payload: dict[str, Any]


@dataclass(slots=True)
class DecisionReport:
    report_id: str
    symbol: str
    interval: str
    created_at_ms: int
    final_action: str
    risk_level: str
    evidence_summary: str
    supervisor_explanation: str
    agent_reports: list[AgentReport]
    retrieved_memory_count: int
    report_summary: str


@dataclass(slots=True)
class MemoryDocument:
    memory_id: int | None
    kind: str
    symbol: str
    interval: str
    created_at_ms: int
    source_report_id: str
    content: str
    metadata: dict[str, Any]


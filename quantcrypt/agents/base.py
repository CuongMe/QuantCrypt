from __future__ import annotations

from typing import Any

from ..llm import ChatModel
from ..observability import AgentEventPhase, LiveMonitor


class AgentNode:
    name: str

    def __init__(self, name: str, llm: ChatModel, monitor: LiveMonitor | None = None) -> None:
        self.name = name
        self.llm = llm
        self.monitor = monitor

    def _log_started(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        if self.monitor is not None:
            self.monitor.record_agent_event(
                agent_name=self.name,
                phase=AgentEventPhase.STARTED,
                message=message,
                metadata=metadata,
            )

    def _log_completed(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        if self.monitor is not None:
            self.monitor.record_agent_event(
                agent_name=self.name,
                phase=AgentEventPhase.COMPLETED,
                message=message,
                metadata=metadata,
            )

    def _log_failed(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        if self.monitor is not None:
            self.monitor.record_agent_event(
                agent_name=self.name,
                phase=AgentEventPhase.FAILED,
                message=message,
                metadata=metadata,
            )

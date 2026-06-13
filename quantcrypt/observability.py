from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ComponentHealthStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    HEALTHY = "healthy"
    WARNING = "warning"
    FAILED = "failed"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"


class AgentEventPhase(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    INFO = "info"


@dataclass(slots=True, frozen=True)
class AgentLogEntry:
    timestamp_ms: int
    run_id: str | None
    agent_name: str
    phase: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class AlertEntry:
    timestamp_ms: int
    run_id: str | None
    severity: str
    source: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ComponentStatusEntry:
    component_name: str
    status: str
    message: str
    updated_at_ms: int


@dataclass(slots=True, frozen=True)
class LiveMonitorSnapshot:
    run_id: str | None
    mode: str | None
    symbol: str | None
    interval: str | None
    agent_logs: list[AgentLogEntry]
    alerts: list[AlertEntry]
    component_statuses: list[ComponentStatusEntry]


class LiveMonitor:
    def __init__(self, *, max_agent_logs: int = 500, max_alerts: int = 100) -> None:
        self._lock = threading.Lock()
        self._agent_logs: deque[AgentLogEntry] = deque(maxlen=max_agent_logs)
        self._alerts: deque[AlertEntry] = deque(maxlen=max_alerts)
        self._component_statuses: dict[str, ComponentStatusEntry] = {}
        self._run_id: str | None = None
        self._mode: str | None = None
        self._symbol: str | None = None
        self._interval: str | None = None

    def start_run(self, *, mode: str, symbol: str, interval: str) -> str:
        run_id = str(uuid.uuid4())
        with self._lock:
            self._run_id = run_id
            self._mode = mode
            self._symbol = symbol
            self._interval = interval
        self.set_component_status(
            "dashboard_runner",
            status=ComponentHealthStatus.RUNNING,
            message=f"Running {mode} for {symbol} {interval}.",
        )
        self.record_agent_event(
            agent_name="dashboard_runner",
            phase=AgentEventPhase.INFO,
            message=f"Started {mode} run for {symbol} {interval}.",
        )
        return run_id

    def finish_run(self, *, status: ComponentHealthStatus, message: str) -> None:
        self.set_component_status("dashboard_runner", status=status, message=message)

    def set_component_status(self, component_name: str, *, status: ComponentHealthStatus, message: str) -> None:
        with self._lock:
            self._component_statuses[component_name] = ComponentStatusEntry(
                component_name=component_name,
                status=status.value,
                message=message,
                updated_at_ms=self._now_ms(),
            )

    def record_alert(
        self,
        *,
        severity: AlertSeverity,
        source: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._alerts.append(
                AlertEntry(
                    timestamp_ms=self._now_ms(),
                    run_id=self._run_id,
                    severity=severity.value,
                    source=source,
                    message=message,
                    details=details or {},
                )
            )

    def record_agent_event(
        self,
        *,
        agent_name: str,
        phase: AgentEventPhase,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._agent_logs.append(
                AgentLogEntry(
                    timestamp_ms=self._now_ms(),
                    run_id=self._run_id,
                    agent_name=agent_name,
                    phase=phase.value,
                    message=message,
                    metadata=metadata or {},
                )
            )
            if phase == AgentEventPhase.STARTED:
                component_status = ComponentHealthStatus.RUNNING
            elif phase == AgentEventPhase.COMPLETED:
                component_status = ComponentHealthStatus.HEALTHY
            elif phase == AgentEventPhase.FAILED:
                component_status = ComponentHealthStatus.FAILED
            else:
                existing = self._component_statuses.get(agent_name)
                component_status = (
                    ComponentHealthStatus(existing.status)
                    if existing is not None
                    else ComponentHealthStatus.HEALTHY
                )

            self._component_statuses[agent_name] = ComponentStatusEntry(
                component_name=agent_name,
                status=component_status.value,
                message=message,
                updated_at_ms=self._now_ms(),
            )

    def snapshot(self, *, agent_log_limit: int = 200, alert_limit: int = 50) -> LiveMonitorSnapshot:
        with self._lock:
            return LiveMonitorSnapshot(
                run_id=self._run_id,
                mode=self._mode,
                symbol=self._symbol,
                interval=self._interval,
                agent_logs=list(reversed(list(self._agent_logs)[-agent_log_limit:])),
                alerts=list(reversed(list(self._alerts)[-alert_limit:])),
                component_statuses=list(self._component_statuses.values()),
            )

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

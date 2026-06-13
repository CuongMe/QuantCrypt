from __future__ import annotations

import pytest
from pydantic import BaseModel

from quantcrypt.llm import OllamaChatModel
from quantcrypt.observability import LiveMonitor


class _SamplePayload(BaseModel):
    action: str
    confidence: float


class _FakeRunnable:
    def __init__(self, response: BaseModel | Exception) -> None:
        self._response = response

    def invoke(self, messages):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def test_ollama_invoke_structured_returns_validated_payload(monkeypatch) -> None:
    model = OllamaChatModel(model="gemma4:12b", base_url="http://localhost:11434")
    monkeypatch.setattr(
        OllamaChatModel,
        "_get_structured_runnable",
        lambda self, output_schema: _FakeRunnable(_SamplePayload(action="buy", confidence=0.7)),
    )

    response = model.invoke_structured(
        system_prompt="system",
        user_prompt="user",
        output_schema=_SamplePayload,
    )

    assert response == _SamplePayload(action="buy", confidence=0.7)


def test_ollama_invoke_structured_wraps_validation_failure(monkeypatch) -> None:
    model = OllamaChatModel(model="gemma4:12b", base_url="http://localhost:11434")
    monkeypatch.setattr(
        OllamaChatModel,
        "_get_structured_runnable",
        lambda self, output_schema: _FakeRunnable(ValueError("invalid payload")),
    )

    with pytest.raises(RuntimeError, match="Failed to invoke Ollama"):
        model.invoke_structured(
            system_prompt="system",
            user_prompt="user",
            output_schema=_SamplePayload,
        )


def test_ollama_connection_failure_records_critical_alert(monkeypatch) -> None:
    monitor = LiveMonitor()
    model = OllamaChatModel(
        model="gemma4:12b",
        base_url="http://localhost:11434",
        monitor=monitor,
    )
    monkeypatch.setattr(
        OllamaChatModel,
        "_get_structured_runnable",
        lambda self, output_schema: _FakeRunnable(ConnectionError("connection refused")),
    )

    with pytest.raises(RuntimeError, match="Failed to invoke Ollama"):
        model.invoke_structured(
            system_prompt="system",
            user_prompt="user",
            output_schema=_SamplePayload,
        )

    snapshot = monitor.snapshot()

    assert snapshot.alerts
    assert snapshot.alerts[0].severity == "critical"
    assert snapshot.alerts[0].source == "ollama"
    assert any(entry.component_name == "ollama" and entry.status == "failed" for entry in snapshot.component_statuses)

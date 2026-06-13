from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Protocol, Sequence, TypeVar, cast

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel

from .env import load_local_env
from .observability import AlertSeverity, ComponentHealthStatus, LiveMonitor


load_local_env()

logger = logging.getLogger(__name__)
StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)


class StructuredRunnable(Protocol[StructuredOutputT]):
    def invoke(self, input: Sequence[SystemMessage | HumanMessage]) -> StructuredOutputT:
        ...


class ChatModel(Protocol):
    def invoke_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[StructuredOutputT],
    ) -> StructuredOutputT:
        ...


@dataclass(slots=True)
class OllamaChatModel:
    model: str = "gemma4:12b"
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 120.0
    temperature: float = 0.2
    monitor: LiveMonitor | None = None
    _structured_runnables: dict[type[BaseModel], StructuredRunnable[BaseModel]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    @classmethod
    def from_env(cls) -> "OllamaChatModel":
        return cls(
            model=os.getenv("OLLAMA_MODEL", "gemma4:12b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
        )

    def invoke_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[StructuredOutputT],
    ) -> StructuredOutputT:
        if self.monitor is not None:
            self.monitor.set_component_status(
                "ollama",
                status=ComponentHealthStatus.RUNNING,
                message=f"Requesting structured {output_schema.__name__} response from {self.model}.",
            )

        runnable = self._get_structured_runnable(output_schema)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            parsed_payload = runnable.invoke(messages)
        except Exception as exc:
            message = (
                f"Failed to invoke Ollama at {self.base_url.rstrip('/')}/api/chat "
                f"for model '{self.model}': {exc}"
            )
            logger.exception("Structured Ollama invocation failed for model '%s'.", self.model)
            if self.monitor is not None:
                self.monitor.set_component_status(
                    "ollama",
                    status=ComponentHealthStatus.FAILED,
                    message=message,
                )
                self.monitor.record_alert(
                    severity=AlertSeverity.CRITICAL,
                    source="ollama",
                    message=message,
                    details={
                        "model": self.model,
                        "base_url": self.base_url,
                        "schema": output_schema.__name__,
                    },
                )
            raise RuntimeError(message) from exc

        if self.monitor is not None:
            self.monitor.set_component_status(
                "ollama",
                status=ComponentHealthStatus.HEALTHY,
                message=f"Ollama responded successfully with model {self.model}.",
            )
        return parsed_payload

    def _get_structured_runnable(self, output_schema: type[StructuredOutputT]):
        runnable = self._structured_runnables.get(output_schema)
        if runnable is None:
            runnable = cast(
                StructuredRunnable[BaseModel],
                self._build_chat_model().with_structured_output(
                    output_schema,
                    method="json_schema",
                ),
            )
            self._structured_runnables[output_schema] = runnable
        return cast(StructuredRunnable[StructuredOutputT], runnable)

    def _build_chat_model(self) -> ChatOllama:
        logger.debug(
            "Creating ChatOllama client for model '%s' at '%s'.",
            self.model,
            self.base_url,
        )
        return ChatOllama(
            model=self.model,
            base_url=self.base_url,
            temperature=self.temperature,
            validate_model_on_init=False,
        )

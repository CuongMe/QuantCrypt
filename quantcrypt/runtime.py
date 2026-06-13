from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .ai_engineering import AIEngineeringNode
from .data_foundation import DataFoundationNode
from .env import load_local_env
from .llm import OllamaChatModel
from .observability import ComponentHealthStatus, LiveMonitor
from .paths import DEFAULT_DB_PATH, DEFAULT_FAISS_INDEX_PATH
from .supervisor import SupervisorNode


load_local_env()


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    db_path: Path = DEFAULT_DB_PATH
    faiss_index_path: Path = DEFAULT_FAISS_INDEX_PATH
    ollama_model: str = "gemma4:12b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(
            db_path=Path(os.getenv("QUANTCRYPT_DB_PATH", str(DEFAULT_DB_PATH))).expanduser(),
            faiss_index_path=Path(
                os.getenv("QUANTCRYPT_FAISS_INDEX_PATH", str(DEFAULT_FAISS_INDEX_PATH))
            ).expanduser(),
            ollama_model=os.getenv("OLLAMA_MODEL", "gemma4:12b"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
        )


@dataclass(slots=True)
class RuntimeServices:
    config: RuntimeConfig
    monitor: LiveMonitor
    llm: OllamaChatModel
    data_foundation: DataFoundationNode
    ai_engineering: AIEngineeringNode
    supervisor: SupervisorNode


class RuntimeFactory:
    def __init__(self, config: RuntimeConfig | None = None) -> None:
        self.config = config or RuntimeConfig.from_env()
        self.monitor = LiveMonitor()
        self._seed_component_statuses()

    def build(self) -> RuntimeServices:
        llm = OllamaChatModel(
            model=self.config.ollama_model,
            base_url=self.config.ollama_base_url,
            timeout_seconds=self.config.ollama_timeout_seconds,
            monitor=self.monitor,
        )
        data_foundation = DataFoundationNode(db_path=self.config.db_path)
        ai_engineering = AIEngineeringNode(
            data_foundation=data_foundation,
            db_path=self.config.db_path,
            faiss_index_path=self.config.faiss_index_path,
        )
        supervisor = SupervisorNode(llm=llm, monitor=self.monitor)
        return RuntimeServices(
            config=self.config,
            monitor=self.monitor,
            llm=llm,
            data_foundation=data_foundation,
            ai_engineering=ai_engineering,
            supervisor=supervisor,
        )

    def _seed_component_statuses(self) -> None:
        self.monitor.set_component_status(
            "dashboard_runner",
            status=ComponentHealthStatus.IDLE,
            message="Ready for a dashboard run.",
        )
        self.monitor.set_component_status(
            "ollama",
            status=ComponentHealthStatus.IDLE,
            message=f"Configured for local model {self.config.ollama_model}.",
        )
        self.monitor.set_component_status(
            "data_sync",
            status=ComponentHealthStatus.IDLE,
            message="No market data sync attempted yet.",
        )
        for agent_name in ("supervisor", "analyst", "researcher", "trader", "risk"):
            self.monitor.set_component_status(
                agent_name,
                status=ComponentHealthStatus.IDLE,
                message="Waiting for execution.",
            )

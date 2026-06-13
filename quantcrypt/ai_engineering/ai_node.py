from __future__ import annotations

import time
import uuid
from pathlib import Path

from ..data_foundation.data_node import DataFoundationNode
from ..models import SupervisorDecision
from ..paths import DEFAULT_DB_PATH, DEFAULT_FAISS_INDEX_PATH
from .embeddings import EmbeddingModel, HashEmbeddingModel
from .evidence import EvidenceBundle
from .faiss_store import FaissVectorStore
from .memory_builder import MemoryBuilder
from .rag import AgenticRAG
from .reports import AgentReport, DecisionReport
from .store import AIEngineeringStore


class AIEngineeringNode:
    def __init__(
        self,
        *,
        data_foundation: DataFoundationNode,
        db_path: str | Path | None = None,
        faiss_index_path: str | Path | None = None,
        store: AIEngineeringStore | None = None,
        vector_store: FaissVectorStore | None = None,
        memory_builder: MemoryBuilder | None = None,
        rag: AgenticRAG | None = None,
        embedding_model: EmbeddingModel | None = None,
    ) -> None:
        self.data_foundation = data_foundation
        resolved_db_path = Path(db_path or data_foundation.store.db_path or DEFAULT_DB_PATH)
        resolved_faiss_path = Path(faiss_index_path or DEFAULT_FAISS_INDEX_PATH)
        shared_embedding_model = embedding_model or HashEmbeddingModel()

        self.store = store or AIEngineeringStore(resolved_db_path)
        self.vector_store = vector_store or FaissVectorStore(
            index_path=resolved_faiss_path,
            embedding_model=shared_embedding_model,
        )
        self.memory_builder = memory_builder or MemoryBuilder()
        self.rag = rag or AgenticRAG(
            data_foundation=self.data_foundation,
            store=self.store,
            vector_store=self.vector_store,
        )

    def build_context(
        self,
        *,
        symbol: str,
        interval: str,
        lookback_candles: int = 64,
        memory_k: int = 4,
    ):
        return self.rag.build_context(
            symbol=symbol,
            interval=interval,
            lookback_candles=lookback_candles,
            memory_k=memory_k,
        )

    def build_context_at(
        self,
        *,
        symbol: str,
        interval: str,
        evaluation_open_time_ms: int,
        lookback_candles: int = 64,
        memory_k: int = 4,
    ):
        candles = self.data_foundation.load_clean_ohlcv(
            symbol=symbol,
            interval=interval,
            end_open_time_ms=evaluation_open_time_ms + 1,
        )
        return self.rag.build_context_from_candles(
            symbol=symbol,
            interval=interval,
            candles=candles[-lookback_candles:],
            memory_k=memory_k,
            memory_before_ms=evaluation_open_time_ms,
        )

    def build_context_from_candles(
        self,
        *,
        symbol: str,
        interval: str,
        candles,
        memory_k: int = 4,
        memory_before_ms: int | None = None,
    ):
        return self.rag.build_context_from_candles(
            symbol=symbol,
            interval=interval,
            candles=candles,
            memory_k=memory_k,
            memory_before_ms=memory_before_ms,
        )

    def build_decision_report(
        self,
        *,
        decision: SupervisorDecision,
        interval: str,
        evidence: EvidenceBundle | None,
    ) -> DecisionReport:
        created_at_ms = int(time.time() * 1000)
        report_id = str(uuid.uuid4())
        agent_reports = [
            AgentReport(
                agent_name="analyst",
                output_summary=" | ".join(item.summary for item in decision.analyst.items),
                payload={
                    "composite_score": decision.analyst.composite_score,
                    "items": [
                        {"category": item.category, "score": item.score, "summary": item.summary}
                        for item in decision.analyst.items
                    ],
                },
            ),
            AgentReport(
                agent_name="researcher",
                output_summary=(
                    f"Bullish: {', '.join(decision.researcher.bullish_points)}; "
                    f"Bearish: {', '.join(decision.researcher.bearish_points)}"
                ),
                payload={
                    "bullish_points": decision.researcher.bullish_points,
                    "bearish_points": decision.researcher.bearish_points,
                    "conviction": decision.researcher.conviction,
                },
            ),
            AgentReport(
                agent_name="trader",
                output_summary=decision.trader.rationale,
                payload={
                    "preliminary_action": decision.trader.preliminary_action.value,
                    "confidence": decision.trader.confidence,
                    "rationale": decision.trader.rationale,
                },
            ),
            AgentReport(
                agent_name="risk",
                output_summary=decision.risk.rationale,
                payload={
                    "risk_level": decision.risk.risk_level.value,
                    "approved": decision.risk.approved,
                    "rationale": decision.risk.rationale,
                },
            ),
        ]
        evidence_summary = evidence.report_summary if evidence else decision.explanation
        report_summary = (
            f"{decision.context.symbol} {interval}: supervisor finalized {decision.final_action.value}. "
            f"{decision.explanation}"
        )
        return DecisionReport(
            report_id=report_id,
            symbol=decision.context.symbol,
            interval=interval,
            created_at_ms=created_at_ms,
            final_action=decision.final_action.value,
            risk_level=decision.risk.risk_level.value,
            evidence_summary=evidence_summary,
            supervisor_explanation=decision.explanation,
            agent_reports=agent_reports,
            retrieved_memory_count=len(evidence.retrieved_memories) if evidence else 0,
            report_summary=report_summary,
        )

    def persist_decision(
        self,
        *,
        decision: SupervisorDecision,
        interval: str,
        evidence: EvidenceBundle | None,
    ) -> DecisionReport:
        report = self.build_decision_report(decision=decision, interval=interval, evidence=evidence)
        self.store.insert_decision_report(report)
        self.memory_builder.persist_report_memories(
            report=report,
            store=self.store,
            vector_store=self.vector_store,
        )
        return report

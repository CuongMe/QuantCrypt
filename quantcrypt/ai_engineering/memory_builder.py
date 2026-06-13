from __future__ import annotations

from .reports import DecisionReport, MemoryDocument
from .store import AIEngineeringStore
from .faiss_store import FaissVectorStore


class MemoryBuilder:
    def build_memory_documents(self, report: DecisionReport) -> list[MemoryDocument]:
        agent_payloads = {agent.agent_name: agent for agent in report.agent_reports}
        return [
            MemoryDocument(
                memory_id=None,
                kind="market_summary",
                symbol=report.symbol,
                interval=report.interval,
                created_at_ms=report.created_at_ms,
                source_report_id=report.report_id,
                content=f"Market summary for {report.symbol} {report.interval}: {report.evidence_summary}",
                metadata={"final_action": report.final_action, "risk_level": report.risk_level},
            ),
            MemoryDocument(
                memory_id=None,
                kind="research_note",
                symbol=report.symbol,
                interval=report.interval,
                created_at_ms=report.created_at_ms,
                source_report_id=report.report_id,
                content=(
                    f"Research note for {report.symbol}: "
                    f"{agent_payloads['researcher'].output_summary if 'researcher' in agent_payloads else report.report_summary}"
                ),
                metadata={"final_action": report.final_action},
            ),
            MemoryDocument(
                memory_id=None,
                kind="risk_verdict",
                symbol=report.symbol,
                interval=report.interval,
                created_at_ms=report.created_at_ms,
                source_report_id=report.report_id,
                content=(
                    f"Risk verdict for {report.symbol}: "
                    f"{agent_payloads['risk'].output_summary if 'risk' in agent_payloads else report.risk_level}"
                ),
                metadata={"risk_level": report.risk_level},
            ),
            MemoryDocument(
                memory_id=None,
                kind="decision_summary",
                symbol=report.symbol,
                interval=report.interval,
                created_at_ms=report.created_at_ms,
                source_report_id=report.report_id,
                content=(
                    f"Decision summary for {report.symbol}: final action {report.final_action}; "
                    f"{report.supervisor_explanation}"
                ),
                metadata={"final_action": report.final_action, "retrieved_memory_count": report.retrieved_memory_count},
            ),
        ]

    def persist_report_memories(
        self,
        *,
        report: DecisionReport,
        store: AIEngineeringStore,
        vector_store: FaissVectorStore,
    ) -> int:
        documents = self.build_memory_documents(report)
        inserted = store.insert_memory_documents(documents)
        vector_store.add_memory_documents(inserted)
        return len(inserted)


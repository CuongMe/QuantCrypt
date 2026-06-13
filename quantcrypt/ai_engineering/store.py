from __future__ import annotations

import json
from pathlib import Path

from ..sqlite_utils import connect_sqlite, initialize_sqlite_schema, prepare_sqlite_path
from .reports import AgentReport, DecisionReport, MemoryDocument


class AIEngineeringStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = prepare_sqlite_path(db_path)
        self.initialize_schema()

    def _connect(self):
        return connect_sqlite(self.db_path)

    def initialize_schema(self) -> None:
        initialize_sqlite_schema(
            self.db_path,
            """
            CREATE TABLE IF NOT EXISTS decision_reports (
                report_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                created_at_ms INTEGER NOT NULL,
                final_action TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                evidence_summary TEXT NOT NULL,
                supervisor_explanation TEXT NOT NULL,
                retrieved_memory_count INTEGER NOT NULL,
                report_summary TEXT NOT NULL,
                report_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_reports (
                report_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                output_summary TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (report_id, agent_name),
                FOREIGN KEY (report_id) REFERENCES decision_reports(report_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS memory_documents (
                memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_report_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                kind TEXT NOT NULL,
                created_at_ms INTEGER NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memory_documents_symbol
            ON memory_documents (symbol, interval, created_at_ms DESC);
            """,
        )

    def insert_decision_report(self, report: DecisionReport) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO decision_reports (
                    report_id, symbol, interval, created_at_ms, final_action, risk_level,
                    evidence_summary, supervisor_explanation, retrieved_memory_count,
                    report_summary, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.symbol,
                    report.interval,
                    report.created_at_ms,
                    report.final_action,
                    report.risk_level,
                    report.evidence_summary,
                    report.supervisor_explanation,
                    report.retrieved_memory_count,
                    report.report_summary,
                    json.dumps(
                        {
                            "report_id": report.report_id,
                            "symbol": report.symbol,
                            "interval": report.interval,
                            "created_at_ms": report.created_at_ms,
                            "final_action": report.final_action,
                            "risk_level": report.risk_level,
                            "evidence_summary": report.evidence_summary,
                            "supervisor_explanation": report.supervisor_explanation,
                            "retrieved_memory_count": report.retrieved_memory_count,
                            "report_summary": report.report_summary,
                        }
                    ),
                ),
            )
            connection.executemany(
                """
                INSERT OR REPLACE INTO agent_reports (
                    report_id, agent_name, output_summary, payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        report.report_id,
                        agent_report.agent_name,
                        agent_report.output_summary,
                        json.dumps(agent_report.payload),
                    )
                    for agent_report in report.agent_reports
                ],
            )

    def insert_memory_documents(self, documents: list[MemoryDocument]) -> list[MemoryDocument]:
        inserted: list[MemoryDocument] = []
        if not documents:
            return inserted
        with self._connect() as connection:
            for document in documents:
                cursor = connection.execute(
                    """
                    INSERT INTO memory_documents (
                        source_report_id, symbol, interval, kind, created_at_ms, content, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document.source_report_id,
                        document.symbol,
                        document.interval,
                        document.kind,
                        document.created_at_ms,
                        document.content,
                        json.dumps(document.metadata),
                    ),
                )
                inserted.append(
                    MemoryDocument(
                        memory_id=int(cursor.lastrowid),
                        kind=document.kind,
                        symbol=document.symbol,
                        interval=document.interval,
                        created_at_ms=document.created_at_ms,
                        source_report_id=document.source_report_id,
                        content=document.content,
                        metadata=document.metadata,
                    )
                )
        return inserted

    def fetch_memory_documents(self, memory_ids: list[int]) -> list[MemoryDocument]:
        if not memory_ids:
            return []
        placeholders = ",".join("?" for _ in memory_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT memory_id, source_report_id, symbol, interval, kind, created_at_ms, content, metadata_json
                FROM memory_documents
                WHERE memory_id IN ({placeholders})
                """,
                memory_ids,
            ).fetchall()
        by_id = {
            int(row["memory_id"]): MemoryDocument(
                memory_id=int(row["memory_id"]),
                source_report_id=row["source_report_id"],
                symbol=row["symbol"],
                interval=row["interval"],
                kind=row["kind"],
                created_at_ms=int(row["created_at_ms"]),
                content=row["content"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        }
        return [by_id[memory_id] for memory_id in memory_ids if memory_id in by_id]

    def count_decision_reports(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM decision_reports").fetchone()[0])

    def count_memory_documents(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM memory_documents").fetchone()[0])

    def fetch_recent_decision_reports(
        self,
        *,
        limit: int = 10,
        symbol: str | None = None,
        interval: str | None = None,
    ) -> list[DecisionReport]:
        if limit <= 0:
            return []

        clauses: list[str] = []
        params: list[object] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if interval:
            clauses.append("interval = ?")
            params.append(interval)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT report_id, symbol, interval, created_at_ms, final_action, risk_level,
                       evidence_summary, supervisor_explanation, retrieved_memory_count, report_summary
                FROM decision_reports
                {where_clause}
                ORDER BY created_at_ms DESC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
            report_ids = [str(row["report_id"]) for row in rows]
            agent_rows = []
            if report_ids:
                placeholders = ",".join("?" for _ in report_ids)
                agent_rows = connection.execute(
                    f"""
                    SELECT report_id, agent_name, output_summary, payload_json
                    FROM agent_reports
                    WHERE report_id IN ({placeholders})
                    ORDER BY report_id, agent_name
                    """,
                    report_ids,
                ).fetchall()

        agent_reports_by_report_id: dict[str, list[AgentReport]] = {}
        for row in agent_rows:
            agent_reports_by_report_id.setdefault(str(row["report_id"]), []).append(
                AgentReport(
                    agent_name=row["agent_name"],
                    output_summary=row["output_summary"],
                    payload=json.loads(row["payload_json"]),
                )
            )

        return [
            DecisionReport(
                report_id=str(row["report_id"]),
                symbol=row["symbol"],
                interval=row["interval"],
                created_at_ms=int(row["created_at_ms"]),
                final_action=row["final_action"],
                risk_level=row["risk_level"],
                evidence_summary=row["evidence_summary"],
                supervisor_explanation=row["supervisor_explanation"],
                agent_reports=agent_reports_by_report_id.get(str(row["report_id"]), []),
                retrieved_memory_count=int(row["retrieved_memory_count"]),
                report_summary=row["report_summary"],
            )
            for row in rows
        ]

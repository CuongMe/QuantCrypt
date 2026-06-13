from __future__ import annotations

from ..data_foundation.data_node import DataFoundationNode
from ..models import MarketContext
from .evidence import EvidenceBundle, RetrievedMemoryHit, build_market_evidence
from .faiss_store import FaissVectorStore
from .store import AIEngineeringStore


class AgenticRAG:
    def __init__(
        self,
        *,
        data_foundation: DataFoundationNode,
        store: AIEngineeringStore,
        vector_store: FaissVectorStore,
    ) -> None:
        self.data_foundation = data_foundation
        self.store = store
        self.vector_store = vector_store

    def build_context(
        self,
        *,
        symbol: str,
        interval: str,
        lookback_candles: int = 64,
        memory_k: int = 4,
    ) -> tuple[MarketContext, EvidenceBundle]:
        candles = self.data_foundation.load_latest_clean_ohlcv(
            symbol=symbol,
            interval=interval,
            limit=lookback_candles,
        )
        return self.build_context_from_candles(
            symbol=symbol,
            interval=interval,
            candles=candles,
            memory_k=memory_k,
        )

    def build_context_from_candles(
        self,
        *,
        symbol: str,
        interval: str,
        candles,
        memory_k: int = 4,
        memory_before_ms: int | None = None,
    ) -> tuple[MarketContext, EvidenceBundle]:
        market = build_market_evidence(symbol=symbol, interval=interval, candles=candles)
        query_text = f"{symbol} {interval} {market.summary}"
        hits = self._retrieve_memory_hits(
            query_text,
            memory_k=memory_k,
            created_before_ms=memory_before_ms,
        )

        evidence = EvidenceBundle(
            market=market,
            retrieved_memories=hits,
            report_summary=(
                f"Structured market evidence: {market.summary} "
                f"Retrieved memory count: {len(hits)}."
            ),
        )
        context = MarketContext(
            symbol=symbol,
            fundamental_signal=0.0,
            sentiment_signal=0.0,
            news_signal=0.0,
            technical_signal=market.technical_signal,
            volatility_signal=market.volatility_signal,
            fundamental_context="No fundamental dataset is connected in the current architecture.",
            sentiment_context="No sentiment dataset is connected in the current architecture.",
            news_context="No news dataset is connected in the current architecture.",
            technical_context=evidence.to_prompt_context(),
        )
        return context, evidence

    def _retrieve_memory_hits(
        self,
        query_text: str,
        *,
        memory_k: int,
        created_before_ms: int | None = None,
    ) -> list[RetrievedMemoryHit]:
        if memory_k <= 0:
            return []

        search_k = max(memory_k * 4, memory_k)
        raw_hits = self.vector_store.search(query_text, top_k=search_k)
        memory_docs = self.store.fetch_memory_documents([memory_id for memory_id, _ in raw_hits])
        by_id = {document.memory_id: document for document in memory_docs}

        filtered_hits: list[RetrievedMemoryHit] = []
        for memory_id, score in raw_hits:
            document = by_id.get(memory_id)
            if document is None:
                continue
            if created_before_ms is not None and document.created_at_ms > created_before_ms:
                continue
            filtered_hits.append(
                RetrievedMemoryHit(
                    memory_id=memory_id,
                    kind=document.kind,
                    score=score,
                    content=document.content,
                    metadata=document.metadata,
                )
            )
            if len(filtered_hits) >= memory_k:
                break
        return filtered_hits

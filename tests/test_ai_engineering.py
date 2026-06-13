from __future__ import annotations

from pathlib import Path

from quantcrypt.ai_engineering import AIEngineeringNode
from quantcrypt.data_foundation.models import OHLCVCandle
from quantcrypt.data_foundation.node import DataFoundationNode
from quantcrypt.data_foundation.storage import SQLiteOHLCVStore
from quantcrypt.supervisor import SupervisorNode


class StubLLM:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)

    def invoke_structured(self, *, system_prompt: str, user_prompt: str, output_schema):
        if not self._responses:
            raise AssertionError("No more stub responses available")
        return output_schema.model_validate(self._responses.pop(0))


def _make_candle(open_time_ms: int, close_price: float, volume: float) -> OHLCVCandle:
    return OHLCVCandle(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        interval="1m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 59_999,
        open_price=close_price - 0.5,
        high_price=close_price + 1.0,
        low_price=close_price - 1.0,
        close_price=close_price,
        volume=volume,
        quote_asset_volume=close_price * volume,
        trade_count=20,
        taker_buy_base_volume=volume / 2,
        taker_buy_quote_volume=(close_price * volume) / 2,
        is_closed=True,
        source="rest",
    )


def _seed_data_foundation(tmp_path: Path) -> tuple[DataFoundationNode, Path]:
    db_path = tmp_path / "quantcrypt.sqlite3"
    store = SQLiteOHLCVStore(db_path)
    candles = [
        _make_candle(index * 60_000, 100.0 + index, 10.0 + index)
        for index in range(12)
    ]
    store.upsert_candles(candles)
    return DataFoundationNode(db_path=db_path, store=store), db_path


def test_ai_engineering_builds_context_from_sql_candles(tmp_path: Path) -> None:
    data_foundation, db_path = _seed_data_foundation(tmp_path)
    ai_node = AIEngineeringNode(
        data_foundation=data_foundation,
        db_path=db_path,
        faiss_index_path=tmp_path / "memory.faiss",
    )

    context, evidence = ai_node.build_context(symbol="BTCUSDT", interval="1m", lookback_candles=10)

    assert context.symbol == "BTCUSDT"
    assert context.technical_signal > 0.0
    assert context.volatility_signal >= 0.0
    assert "Latest close" in evidence.market.summary or "latest close" in evidence.market.summary
    assert evidence.retrieved_memories == []


def test_run_for_symbol_persists_report_and_builds_faiss_memory(tmp_path: Path) -> None:
    data_foundation, db_path = _seed_data_foundation(tmp_path)
    ai_node = AIEngineeringNode(
        data_foundation=data_foundation,
        db_path=db_path,
        faiss_index_path=tmp_path / "memory.faiss",
    )
    supervisor = SupervisorNode(
        llm=StubLLM(
            [
                {
                    "items": [
                        {"category": "fundamental", "score": 0.0, "summary": "no fundamental feed"},
                        {"category": "sentiment", "score": 0.0, "summary": "no sentiment feed"},
                        {"category": "news", "score": 0.0, "summary": "no news feed"},
                        {"category": "technical", "score": 0.7, "summary": "uptrend in candles"},
                    ],
                    "composite_score": 0.175,
                },
                {
                    "bullish_points": ["trend is constructive"],
                    "bearish_points": ["missing non-price data"],
                    "conviction": 0.25,
                },
                {
                    "preliminary_action": "buy",
                    "confidence": 0.72,
                    "rationale": "price trend supports a cautious long",
                },
                {
                    "risk_level": "medium",
                    "approved": True,
                    "rationale": "volatility is acceptable for a paper trade",
                },
            ]
        )
    )

    decision, report = supervisor.run_for_symbol(
        symbol="BTCUSDT",
        interval="1m",
        ai_engineering=ai_node,
        lookback_candles=10,
        memory_k=4,
    )

    assert decision.report_id == report.report_id
    assert ai_node.store.count_decision_reports() == 1
    assert ai_node.store.count_memory_documents() == 4

    _, evidence = ai_node.build_context(symbol="BTCUSDT", interval="1m", lookback_candles=10, memory_k=4)
    assert len(evidence.retrieved_memories) >= 1
    assert any(hit.kind == "decision_summary" for hit in evidence.retrieved_memories)

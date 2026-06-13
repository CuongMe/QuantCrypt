from __future__ import annotations

from pathlib import Path

from quantcrypt.ai_engineering.ai_node import AIEngineeringNode
from quantcrypt.dashboard.service import DashboardMode, RunConfig, execute_backtest
from quantcrypt.data_foundation.models import OHLCVCandle
from quantcrypt.data_foundation.data_node import DataFoundationNode
from quantcrypt.data_foundation.storage import SQLiteOHLCVStore
from quantcrypt.observability import LiveMonitor
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
        for index in range(20)
    ]
    store.upsert_candles(candles)
    return DataFoundationNode(db_path=db_path, store=store), db_path


def test_execute_backtest_is_read_only_and_returns_summary(tmp_path: Path) -> None:
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
                        {"category": "technical", "score": 0.7, "summary": "uptrend"},
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
            * 5
        )
    )

    summary = execute_backtest(
        data_foundation=data_foundation,
        ai_engineering=ai_node,
        supervisor=supervisor,
        config=RunConfig(
            mode=DashboardMode.BACKTEST,
            symbol="BTCUSDT",
            interval="1m",
            lookback_candles=10,
            backtest_candles=5,
            memory_k=2,
        ),
    )

    assert summary.total_cycles == 5
    assert summary.buy_count == 5
    assert summary.sell_count == 0
    assert summary.hold_count == 0
    assert ai_node.store.count_decision_reports() == 0
    assert ai_node.store.count_memory_documents() == 0


def test_fetch_recent_decision_reports_returns_agent_payloads(tmp_path: Path) -> None:
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
                        {"category": "technical", "score": 0.7, "summary": "uptrend"},
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

    supervisor.run_for_symbol(
        symbol="BTCUSDT",
        interval="1m",
        ai_engineering=ai_node,
        lookback_candles=10,
        memory_k=2,
    )

    reports = ai_node.store.fetch_recent_decision_reports(limit=1, symbol="BTCUSDT", interval="1m")

    assert len(reports) == 1
    assert reports[0].agent_reports
    assert {report.agent_name for report in reports[0].agent_reports} == {
        "analyst",
        "researcher",
        "risk",
        "trader",
    }


def test_execute_backtest_emits_monitor_activity(tmp_path: Path) -> None:
    data_foundation, db_path = _seed_data_foundation(tmp_path)
    ai_node = AIEngineeringNode(
        data_foundation=data_foundation,
        db_path=db_path,
        faiss_index_path=tmp_path / "memory.faiss",
    )
    monitor = LiveMonitor()
    supervisor = SupervisorNode(
        llm=StubLLM(
            [
                {
                    "items": [
                        {"category": "fundamental", "score": 0.0, "summary": "no fundamental feed"},
                        {"category": "sentiment", "score": 0.0, "summary": "no sentiment feed"},
                        {"category": "news", "score": 0.0, "summary": "no news feed"},
                        {"category": "technical", "score": 0.7, "summary": "uptrend"},
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
            * 3
        ),
        monitor=monitor,
    )

    execute_backtest(
        data_foundation=data_foundation,
        ai_engineering=ai_node,
        supervisor=supervisor,
        config=RunConfig(
            mode=DashboardMode.BACKTEST,
            symbol="BTCUSDT",
            interval="1m",
            lookback_candles=10,
            backtest_candles=3,
            memory_k=2,
        ),
    )

    snapshot = monitor.snapshot()

    assert snapshot.agent_logs
    assert any(entry.agent_name == "trader" for entry in snapshot.agent_logs)

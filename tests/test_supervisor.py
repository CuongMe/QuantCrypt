from __future__ import annotations

from quantcrypt.models import MarketContext, RiskLevel, TradeAction
from quantcrypt.observability import LiveMonitor
from quantcrypt.supervisor import SupervisorNode


class StubLLM:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)

    def invoke_structured(self, *, system_prompt: str, user_prompt: str, output_schema):
        if not self._responses:
            raise AssertionError("No more stub responses available")
        return output_schema.model_validate(self._responses.pop(0))


def test_supervisor_runs_layer_one_in_order() -> None:
    supervisor = SupervisorNode(
        llm=StubLLM(
            [
                {
                    "items": [
                        {"category": "fundamental", "score": 0.2, "summary": "fundamental"},
                        {"category": "sentiment", "score": 0.1, "summary": "sentiment"},
                        {"category": "news", "score": -0.1, "summary": "news"},
                        {"category": "technical", "score": 0.0, "summary": "technical"},
                    ],
                    "composite_score": 0.05,
                },
                {
                    "bullish_points": ["small upside"],
                    "bearish_points": ["small downside"],
                    "conviction": 0.05,
                },
                {
                    "preliminary_action": "hold",
                    "confidence": 0.2,
                    "rationale": "mixed case",
                },
                {
                    "risk_level": "low",
                    "approved": True,
                    "rationale": "no active trade",
                },
            ]
        )
    )
    decision = supervisor.run(MarketContext(symbol="BTCUSDT"))

    assert decision.trace == ["analyst", "researcher", "trader", "risk", "supervisor"]


def test_supervisor_keeps_bullish_trade_when_risk_is_low() -> None:
    supervisor = SupervisorNode(
        llm=StubLLM(
            [
                {
                    "items": [
                        {"category": "fundamental", "score": 0.8, "summary": "strong fundamentals"},
                        {"category": "sentiment", "score": 0.4, "summary": "positive sentiment"},
                        {"category": "news", "score": 0.6, "summary": "good news"},
                        {"category": "technical", "score": 0.5, "summary": "trend up"},
                    ],
                    "composite_score": 0.575,
                },
                {
                    "bullish_points": ["momentum strong"],
                    "bearish_points": ["some profit-taking risk"],
                    "conviction": 0.6,
                },
                {
                    "preliminary_action": "buy",
                    "confidence": 0.84,
                    "rationale": "aligned bullish case",
                },
                {
                    "risk_level": "low",
                    "approved": True,
                    "rationale": "risk acceptable",
                },
            ]
        )
    )
    context = MarketContext(
        symbol="BTCUSDT",
        fundamental_signal=0.8,
        sentiment_signal=0.4,
        news_signal=0.6,
        technical_signal=0.5,
        volatility_signal=0.2,
    )

    decision = supervisor.run(context)

    assert decision.trader.preliminary_action == TradeAction.BUY
    assert decision.risk.risk_level == RiskLevel.LOW
    assert decision.final_action == TradeAction.BUY


def test_supervisor_blocks_trade_when_risk_is_high() -> None:
    supervisor = SupervisorNode(
        llm=StubLLM(
            [
                {
                    "items": [
                        {"category": "fundamental", "score": 0.7, "summary": "strong"},
                        {"category": "sentiment", "score": 0.6, "summary": "good"},
                        {"category": "news", "score": 0.5, "summary": "supportive"},
                        {"category": "technical", "score": 0.4, "summary": "bullish"},
                    ],
                    "composite_score": 0.55,
                },
                {
                    "bullish_points": ["bull case"],
                    "bearish_points": ["macro risk"],
                    "conviction": 0.5,
                },
                {
                    "preliminary_action": "buy",
                    "confidence": 0.8,
                    "rationale": "buy candidate",
                },
                {
                    "risk_level": "high",
                    "approved": False,
                    "rationale": "volatility too high",
                },
            ]
        )
    )
    context = MarketContext(
        symbol="BTCUSDT",
        fundamental_signal=0.7,
        sentiment_signal=0.6,
        news_signal=0.5,
        technical_signal=0.4,
        volatility_signal=0.9,
    )

    decision = supervisor.run(context)

    assert decision.trader.preliminary_action == TradeAction.BUY
    assert decision.risk.risk_level == RiskLevel.HIGH
    assert decision.final_action == TradeAction.HOLD


def test_supervisor_can_return_sell() -> None:
    supervisor = SupervisorNode(
        llm=StubLLM(
            [
                {
                    "items": [
                        {"category": "fundamental", "score": -0.8, "summary": "weak fundamentals"},
                        {"category": "sentiment", "score": -0.4, "summary": "negative sentiment"},
                        {"category": "news", "score": -0.5, "summary": "bad news"},
                        {"category": "technical", "score": -0.6, "summary": "trend down"},
                    ],
                    "composite_score": -0.575,
                },
                {
                    "bullish_points": ["bounce possible"],
                    "bearish_points": ["trend is weak"],
                    "conviction": -0.6,
                },
                {
                    "preliminary_action": "sell",
                    "confidence": 0.82,
                    "rationale": "bear case dominates",
                },
                {
                    "risk_level": "medium",
                    "approved": True,
                    "rationale": "sell allowed",
                },
            ]
        )
    )
    context = MarketContext(
        symbol="ETHUSDT",
        fundamental_signal=-0.8,
        sentiment_signal=-0.4,
        news_signal=-0.5,
        technical_signal=-0.6,
        volatility_signal=0.3,
    )

    decision = supervisor.run(context)

    assert decision.trader.preliminary_action == TradeAction.SELL
    assert decision.final_action == TradeAction.SELL


def test_supervisor_emits_agent_activity_logs() -> None:
    monitor = LiveMonitor()
    supervisor = SupervisorNode(
        llm=StubLLM(
            [
                {
                    "items": [
                        {"category": "fundamental", "score": 0.1, "summary": "mild fundamental tailwind"},
                        {"category": "sentiment", "score": 0.0, "summary": "neutral sentiment"},
                        {"category": "news", "score": 0.0, "summary": "no major headlines"},
                        {"category": "technical", "score": 0.4, "summary": "short-term trend up"},
                    ],
                    "composite_score": 0.125,
                },
                {
                    "bullish_points": ["trend is improving"],
                    "bearish_points": ["conviction is still limited"],
                    "conviction": 0.15,
                },
                {
                    "preliminary_action": "buy",
                    "confidence": 0.62,
                    "rationale": "modest long bias",
                },
                {
                    "risk_level": "medium",
                    "approved": True,
                    "rationale": "acceptable for paper execution",
                },
            ]
        ),
        monitor=monitor,
    )

    decision = supervisor.run(MarketContext(symbol="BTCUSDT", technical_signal=0.4, volatility_signal=0.3))
    snapshot = monitor.snapshot()
    agent_names = {entry.agent_name for entry in snapshot.agent_logs}

    assert decision.final_action == TradeAction.BUY
    assert {"supervisor", "analyst", "researcher", "trader", "risk"} <= agent_names
    assert any(entry.agent_name == "analyst" and entry.phase == "started" for entry in snapshot.agent_logs)
    assert any(entry.agent_name == "risk" and entry.phase == "completed" for entry in snapshot.agent_logs)


def test_supervisor_handles_incomplete_researcher_payload_without_crashing() -> None:
    supervisor = SupervisorNode(
        llm=StubLLM(
            [
                {
                    "items": [
                        {"category": "fundamental", "score": 0.2, "summary": "stable fundamentals"},
                        {"category": "sentiment", "score": 0.1, "summary": "slightly positive sentiment"},
                        {"category": "news", "score": 0.0, "summary": "quiet news flow"},
                        {"category": "technical", "score": 0.3, "summary": "modest uptrend"},
                    ],
                    "composite_score": 0.15,
                },
                {
                    "bullish_points": ["technical signal is mildly positive", ""],
                },
                {
                    "preliminary_action": "hold",
                    "confidence": 0.41,
                    "rationale": "research output is incomplete so stay neutral",
                },
                {
                    "risk_level": "medium",
                    "approved": True,
                    "rationale": "no live order is being sent",
                },
            ]
        )
    )

    decision = supervisor.run(MarketContext(symbol="BTCUSDT", technical_signal=0.3))

    assert decision.researcher.bullish_points == ["technical signal is mildly positive"]
    assert decision.researcher.bearish_points == []
    assert decision.researcher.conviction == 0.0
    assert decision.final_action == TradeAction.HOLD

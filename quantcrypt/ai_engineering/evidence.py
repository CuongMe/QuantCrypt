from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy

from ..data_foundation.models import OHLCVCandle


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass(slots=True)
class RetrievedMemoryHit:
    memory_id: int
    kind: str
    score: float
    content: str
    metadata: dict[str, Any]


@dataclass(slots=True)
class MarketEvidence:
    symbol: str
    interval: str
    lookback_candles: int
    evaluation_open_time_ms: int
    latest_close: float
    latest_volume: float
    return_1_pct: float
    return_lookback_pct: float
    sma_fast: float
    sma_slow: float
    sma_spread_pct: float
    realized_volatility: float
    latest_range_pct: float
    volume_ratio: float
    technical_signal: float
    volatility_signal: float
    summary: str


@dataclass(slots=True)
class EvidenceBundle:
    market: MarketEvidence
    retrieved_memories: list[RetrievedMemoryHit]
    report_summary: str

    def to_prompt_context(self, *, max_memory_hits: int = 3) -> str:
        memory_lines = [
            f"- [{hit.kind}] {hit.content}"
            for hit in self.retrieved_memories[:max_memory_hits]
        ]
        if not memory_lines:
            memory_lines = ["- No retrieved memory hits"]
        return (
            f"Structured market evidence:\n{self.market.summary}\n\n"
            f"Retrieved memory evidence:\n" + "\n".join(memory_lines)
        )


def build_market_evidence(
    *,
    symbol: str,
    interval: str,
    candles: list[OHLCVCandle],
) -> MarketEvidence:
    if len(candles) < 2:
        raise ValueError("At least two candles are required to build market evidence")

    closes = numpy.array([candle.close_price for candle in candles], dtype="float64")
    highs = numpy.array([candle.high_price for candle in candles], dtype="float64")
    lows = numpy.array([candle.low_price for candle in candles], dtype="float64")
    volumes = numpy.array([candle.volume for candle in candles], dtype="float64")
    latest_candle = candles[-1]

    log_returns = numpy.diff(numpy.log(closes))
    return_1_pct = float((closes[-1] / closes[-2]) - 1.0)
    return_lookback_pct = float((closes[-1] / closes[0]) - 1.0)
    fast_window = min(5, len(closes))
    slow_window = min(20, len(closes))
    sma_fast = float(closes[-fast_window:].mean())
    sma_slow = float(closes[-slow_window:].mean())
    sma_spread_pct = float((sma_fast / sma_slow) - 1.0) if sma_slow else 0.0
    realized_volatility = float(log_returns.std() * numpy.sqrt(len(log_returns))) if len(log_returns) else 0.0
    latest_range_pct = float((highs[-1] - lows[-1]) / closes[-1]) if closes[-1] else 0.0
    trailing_volume_mean = float(volumes[:-1].mean()) if len(volumes) > 1 else float(volumes[-1])
    volume_ratio = float(volumes[-1] / trailing_volume_mean) if trailing_volume_mean else 1.0

    momentum_component = numpy.tanh(return_lookback_pct * 8.0)
    trend_component = numpy.tanh(sma_spread_pct * 16.0)
    volume_component = numpy.tanh((volume_ratio - 1.0) * 1.5)
    technical_signal = _clamp(
        float(0.45 * momentum_component + 0.4 * trend_component + 0.15 * volume_component),
        -1.0,
        1.0,
    )
    volatility_signal = _clamp(float(realized_volatility * 12.0 + latest_range_pct * 4.0), 0.0, 1.0)

    summary = (
        f"{symbol} {interval} latest close {closes[-1]:.4f}; "
        f"1-candle return {return_1_pct:+.2%}; "
        f"lookback return {return_lookback_pct:+.2%}; "
        f"fast/slow SMA spread {sma_spread_pct:+.2%}; "
        f"realized volatility {realized_volatility:.4f}; "
        f"volume ratio {volume_ratio:.2f}; "
        f"derived technical signal {technical_signal:+.2f}; "
        f"derived volatility signal {volatility_signal:.2f}."
    )

    return MarketEvidence(
        symbol=symbol,
        interval=interval,
        lookback_candles=len(candles),
        evaluation_open_time_ms=latest_candle.open_time_ms,
        latest_close=float(closes[-1]),
        latest_volume=float(volumes[-1]),
        return_1_pct=return_1_pct,
        return_lookback_pct=return_lookback_pct,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        sma_spread_pct=sma_spread_pct,
        realized_volatility=realized_volatility,
        latest_range_pct=latest_range_pct,
        volume_ratio=volume_ratio,
        technical_signal=technical_signal,
        volatility_signal=volatility_signal,
        summary=summary,
    )


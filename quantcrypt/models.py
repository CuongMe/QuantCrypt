from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


class TradeAction(StrEnum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AnalysisItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(description="Analysis category such as fundamental, sentiment, news, or technical.")
    score: float = Field(description="Normalized category score in the range [-1, 1].")
    summary: str = Field(description="Short explanation for the category score.")


class AnalystResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AnalysisItemPayload] = Field(description="Exactly four category assessments.")
    composite_score: float = Field(description="Composite analyst score in the range [-1, 1].")


class ResearcherResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullish_points: list[str] = Field(description="Bullish arguments supporting the thesis.")
    bearish_points: list[str] = Field(description="Bearish arguments challenging the thesis.")
    conviction: float = Field(description="Balanced conviction score in the range [-1, 1].")


class TraderResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preliminary_action: Literal["buy", "sell", "hold"] = Field(description="Trader's preliminary action.")
    confidence: float = Field(description="Confidence score in the range [0, 1].")
    rationale: str = Field(description="Short explanation for the preliminary action.")


class RiskResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: Literal["low", "medium", "high"] = Field(description="Risk classification for the proposal.")
    approved: bool = Field(description="Whether the trade is approved by risk management.")
    rationale: str = Field(description="Short explanation for the risk verdict.")


@dataclass(slots=True)
class MarketContext:
    symbol: str
    fundamental_signal: float = 0.0
    sentiment_signal: float = 0.0
    news_signal: float = 0.0
    technical_signal: float = 0.0
    volatility_signal: float = 0.5
    fundamental_context: str = ""
    sentiment_context: str = ""
    news_context: str = ""
    technical_context: str = ""

    def __post_init__(self) -> None:
        self.fundamental_signal = _clamp(self.fundamental_signal, -1.0, 1.0)
        self.sentiment_signal = _clamp(self.sentiment_signal, -1.0, 1.0)
        self.news_signal = _clamp(self.news_signal, -1.0, 1.0)
        self.technical_signal = _clamp(self.technical_signal, -1.0, 1.0)
        self.volatility_signal = _clamp(self.volatility_signal, 0.0, 1.0)


@dataclass(slots=True)
class AnalysisItem:
    category: str
    score: float
    summary: str


@dataclass(slots=True)
class AnalystOutput:
    items: list[AnalysisItem]
    composite_score: float


@dataclass(slots=True)
class ResearchOutput:
    bullish_points: list[str]
    bearish_points: list[str]
    conviction: float


@dataclass(slots=True)
class TraderOutput:
    preliminary_action: TradeAction
    confidence: float
    rationale: str


@dataclass(slots=True)
class RiskOutput:
    risk_level: RiskLevel
    approved: bool
    rationale: str


@dataclass(slots=True)
class SupervisorDecision:
    context: MarketContext
    analyst: AnalystOutput
    researcher: ResearchOutput
    trader: TraderOutput
    risk: RiskOutput
    final_action: TradeAction
    explanation: str
    trace: list[str]
    evidence_summary: str = ""
    retrieved_memory_count: int = 0
    report_id: str | None = None

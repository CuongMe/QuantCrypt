from __future__ import annotations

from .base import AgentNode
from ..ai_engineering.evidence import EvidenceBundle
from ..models import AnalysisItem, AnalystOutput, AnalystResponsePayload, MarketContext
from ..observability import LiveMonitor


class AnalystAgent(AgentNode):
    def __init__(self, llm, monitor: LiveMonitor | None = None) -> None:
        super().__init__("analyst", llm, monitor)

    def run(self, context: MarketContext, evidence: EvidenceBundle | None = None) -> AnalystOutput:
        evidence_block = evidence.to_prompt_context() if evidence is not None else "No structured evidence was provided."
        self._log_started(
            f"Evaluating fundamental, sentiment, news, and technical inputs for {context.symbol}.",
            metadata={
                "symbol": context.symbol,
                "technical_signal": context.technical_signal,
                "volatility_signal": context.volatility_signal,
            },
        )
        try:
            payload = self.llm.invoke_structured(
                system_prompt=(
                    "You are the Analyst Agent in a crypto trading supervisor system. "
                    "Return only JSON with keys items and composite_score. "
                    "items must contain exactly four objects for fundamental, sentiment, news, and technical. "
                    "Each item must include category, score in [-1, 1], and summary."
                ),
                user_prompt=(
                    f"Symbol: {context.symbol}\n"
                    f"Fundamental signal: {context.fundamental_signal}\n"
                    f"Sentiment signal: {context.sentiment_signal}\n"
                    f"News signal: {context.news_signal}\n"
                    f"Technical signal: {context.technical_signal}\n"
                    f"Fundamental context: {context.fundamental_context}\n"
                    f"Sentiment context: {context.sentiment_context}\n"
                    f"News context: {context.news_context}\n"
                    f"Technical context: {context.technical_context}\n"
                    f"Evidence layer context:\n{evidence_block}\n"
                ),
                output_schema=AnalystResponsePayload,
            )
            items = [
                AnalysisItem(
                    category=item.category,
                    score=self._clamp_score(item.score),
                    summary=item.summary,
                )
                for item in payload.items
            ]
            composite_score = self._clamp_score(payload.composite_score)
        except Exception as exc:
            self._log_failed(f"Analyst evaluation failed: {exc}")
            raise

        technical_item = next((item for item in items if item.category == "technical"), None)
        self._log_completed(
            (
                f"Composite score {composite_score:+.2f}. "
                f"Technical view: {technical_item.summary if technical_item is not None else 'no technical summary'}"
            ),
            metadata={"composite_score": composite_score},
        )
        return AnalystOutput(items=items, composite_score=composite_score)

    def _clamp_score(self, score: float) -> float:
        return max(-1.0, min(1.0, score))

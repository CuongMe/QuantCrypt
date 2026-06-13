from __future__ import annotations

from .base import AgentNode
from ..ai_engineering.evidence import EvidenceBundle
from ..models import AnalystOutput, ResearchOutput, TradeAction, TraderOutput, TraderResponsePayload
from ..observability import LiveMonitor


class TraderAgent(AgentNode):
    def __init__(self, llm, monitor: LiveMonitor | None = None) -> None:
        super().__init__("trader", llm, monitor)

    def run(
        self,
        analyst_output: AnalystOutput,
        researcher_output: ResearchOutput,
        evidence: EvidenceBundle | None = None,
    ) -> TraderOutput:
        evidence_block = evidence.to_prompt_context() if evidence is not None else "No structured evidence was provided."
        self._log_started(
            f"Synthesizing trade action from analyst score {analyst_output.composite_score:+.2f} and researcher conviction {researcher_output.conviction:+.2f}.",
            metadata={
                "analyst_composite_score": analyst_output.composite_score,
                "researcher_conviction": researcher_output.conviction,
            },
        )
        try:
            payload = self.llm.invoke_structured(
                system_prompt=(
                    "You are the Trader Agent in a crypto trading supervisor system. "
                    "Return only JSON with keys preliminary_action, confidence, and rationale. "
                    "preliminary_action must be one of buy, sell, or hold. confidence must be in [0, 1]."
                ),
                user_prompt=(
                    f"Analyst composite score: {analyst_output.composite_score:+.2f}\n"
                    f"Researcher conviction: {researcher_output.conviction:+.2f}\n"
                    f"Bullish points: {researcher_output.bullish_points}\n"
                    f"Bearish points: {researcher_output.bearish_points}\n"
                    f"Evidence layer context:\n{evidence_block}\n"
                ),
                output_schema=TraderResponsePayload,
            )
            action = TradeAction(payload.preliminary_action.lower())
            confidence = max(0.0, min(1.0, payload.confidence))
            rationale = payload.rationale
            output = TraderOutput(
                preliminary_action=action,
                confidence=confidence,
                rationale=rationale,
            )
        except Exception as exc:
            self._log_failed(f"Trader synthesis failed: {exc}")
            raise

        self._log_completed(
            f"Proposed {output.preliminary_action.value} with confidence {output.confidence:.2f}.",
            metadata={
                "preliminary_action": output.preliminary_action.value,
                "confidence": output.confidence,
            },
        )
        return output

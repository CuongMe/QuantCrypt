from __future__ import annotations

from .base import AgentNode
from ..ai_engineering.evidence import EvidenceBundle
from ..models import AnalystOutput, ResearchOutput, ResearcherResponsePayload
from ..observability import LiveMonitor


class ResearcherAgent(AgentNode):
    def __init__(self, llm, monitor: LiveMonitor | None = None) -> None:
        super().__init__("researcher", llm, monitor)

    def run(
        self,
        analyst_output: AnalystOutput,
        evidence: EvidenceBundle | None = None,
    ) -> ResearchOutput:
        analyst_summary = "\n".join(
            f"{item.category}: score={item.score:+.2f}; summary={item.summary}"
            for item in analyst_output.items
        )
        evidence_block = evidence.to_prompt_context() if evidence is not None else "No structured evidence was provided."
        self._log_started(
            f"Comparing bullish and bearish cases from analyst score {analyst_output.composite_score:+.2f}.",
            metadata={"analyst_composite_score": analyst_output.composite_score},
        )
        try:
            payload = self.llm.invoke_structured(
                system_prompt=(
                    "You are the Researcher Agent in a crypto trading supervisor system. "
                    "You contain both bullish and bearish reasoning. "
                    "Return only JSON with keys bullish_points, bearish_points, and conviction. "
                    "conviction must be in [-1, 1]."
                ),
                user_prompt=(
                    f"Analyst composite score: {analyst_output.composite_score:+.2f}\n"
                    f"Analyst breakdown:\n{analyst_summary}\n"
                    f"Evidence layer context:\n{evidence_block}\n"
                ),
                output_schema=ResearcherResponsePayload,
            )
            output = ResearchOutput(
                bullish_points=list(payload.bullish_points),
                bearish_points=list(payload.bearish_points),
                conviction=max(-1.0, min(1.0, payload.conviction)),
            )
        except Exception as exc:
            self._log_failed(f"Researcher evaluation failed: {exc}")
            raise

        self._log_completed(
            f"Generated bullish and bearish cases with conviction {output.conviction:+.2f}.",
            metadata={"conviction": output.conviction},
        )
        return output

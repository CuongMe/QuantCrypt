from __future__ import annotations

from .base import AgentNode
from ..ai_engineering.evidence import EvidenceBundle
from ..models import MarketContext, RiskLevel, RiskOutput, RiskResponsePayload, TradeAction, TraderOutput
from ..observability import LiveMonitor


class RiskManagementAgent(AgentNode):
    def __init__(self, llm, monitor: LiveMonitor | None = None) -> None:
        super().__init__("risk", llm, monitor)

    def run(
        self,
        context: MarketContext,
        trader_output: TraderOutput,
        evidence: EvidenceBundle | None = None,
    ) -> RiskOutput:
        evidence_block = evidence.to_prompt_context() if evidence is not None else "No structured evidence was provided."
        self._log_started(
            f"Assessing risk for {context.symbol} with volatility {context.volatility_signal:.2f}.",
            metadata={
                "symbol": context.symbol,
                "volatility_signal": context.volatility_signal,
                "preliminary_action": trader_output.preliminary_action.value,
            },
        )
        try:
            payload = self.llm.invoke_structured(
                system_prompt=(
                    "You are the Risk Management Agent in a crypto trading supervisor system. "
                    "Return only JSON with keys risk_level, approved, and rationale. "
                    "risk_level must be one of low, medium, or high."
                ),
                user_prompt=(
                    f"Symbol: {context.symbol}\n"
                    f"Volatility signal: {context.volatility_signal}\n"
                    f"Trader action: {trader_output.preliminary_action.value}\n"
                    f"Trader confidence: {trader_output.confidence}\n"
                    f"Trader rationale: {trader_output.rationale}\n"
                    f"Evidence layer context:\n{evidence_block}\n"
                ),
                output_schema=RiskResponsePayload,
            )
            self._log_defaulted_payload_fields(payload)
            output = RiskOutput(
                risk_level=RiskLevel(payload.risk_level.lower()),
                approved=bool(payload.approved),
                rationale=payload.rationale or "Risk model returned incomplete rationale.",
            )
        except Exception as exc:
            self._log_failed(f"Risk evaluation failed: {exc}")
            raise

        self._log_completed(
            f"Classified {output.risk_level.value} risk with approved={output.approved}.",
            metadata={"risk_level": output.risk_level.value, "approved": output.approved},
        )
        return output

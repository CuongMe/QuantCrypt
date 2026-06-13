from __future__ import annotations

from operator import add
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph
from typing_extensions import Annotated, TypedDict

from .agents import AnalystAgent, ResearcherAgent, RiskManagementAgent, TraderAgent
from .ai_engineering.evidence import EvidenceBundle
from .llm import ChatModel, OllamaChatModel
from .models import (
    AnalystOutput,
    MarketContext,
    ResearchOutput,
    RiskOutput,
    SupervisorDecision,
    TradeAction,
    TraderOutput,
)
from .observability import AgentEventPhase, LiveMonitor

if TYPE_CHECKING:
    from .ai_engineering.ai_node import AIEngineeringNode
    from .ai_engineering.reports import DecisionReport


class SupervisorGraphState(TypedDict, total=False):
    context: MarketContext
    evidence: EvidenceBundle | None
    analyst_output: AnalystOutput
    researcher_output: ResearchOutput
    trader_output: TraderOutput
    risk_output: RiskOutput
    final_action: TradeAction
    explanation: str
    trace: Annotated[list[str], add]


class SupervisorNode:
    def __init__(
        self,
        llm: ChatModel | None = None,
        analyst: AnalystAgent | None = None,
        researcher: ResearcherAgent | None = None,
        trader: TraderAgent | None = None,
        risk: RiskManagementAgent | None = None,
        monitor: LiveMonitor | None = None,
    ) -> None:
        shared_llm = llm or OllamaChatModel.from_env()
        shared_monitor = monitor or getattr(shared_llm, "monitor", None)
        self.monitor = shared_monitor
        self.analyst = analyst or AnalystAgent(shared_llm, monitor=shared_monitor)
        self.researcher = researcher or ResearcherAgent(shared_llm, monitor=shared_monitor)
        self.trader = trader or TraderAgent(shared_llm, monitor=shared_monitor)
        self.risk = risk or RiskManagementAgent(shared_llm, monitor=shared_monitor)
        self._graph = self._build_graph()

    def run(
        self,
        context: MarketContext,
        *,
        evidence: EvidenceBundle | None = None,
    ) -> SupervisorDecision:
        if self.monitor is not None:
            self.monitor.record_agent_event(
                agent_name="supervisor",
                phase=AgentEventPhase.STARTED,
                message=f"Starting orchestration for {context.symbol}.",
                metadata={"symbol": context.symbol},
            )

        try:
            final_state = self._graph.invoke(
                {
                    "context": context,
                    "evidence": evidence,
                    "trace": [],
                }
            )
        except Exception as exc:
            if self.monitor is not None:
                self.monitor.record_agent_event(
                    agent_name="supervisor",
                    phase=AgentEventPhase.FAILED,
                    message=f"Supervisor orchestration failed: {exc}",
                    metadata={"symbol": context.symbol},
                )
            raise

        decision = SupervisorDecision(
            context=context,
            analyst=final_state["analyst_output"],
            researcher=final_state["researcher_output"],
            trader=final_state["trader_output"],
            risk=final_state["risk_output"],
            final_action=final_state["final_action"],
            explanation=final_state["explanation"],
            trace=list(final_state.get("trace", [])),
            evidence_summary=evidence.report_summary if evidence is not None else "",
            retrieved_memory_count=len(evidence.retrieved_memories) if evidence is not None else 0,
        )
        if self.monitor is not None:
            self.monitor.record_agent_event(
                agent_name="supervisor",
                phase=AgentEventPhase.COMPLETED,
                message=(
                    f"Finalized {decision.final_action.value} after {decision.trader.preliminary_action.value} "
                    f"with {decision.risk.risk_level.value} risk."
                ),
                metadata={
                    "final_action": decision.final_action.value,
                    "risk_level": decision.risk.risk_level.value,
                },
            )
        return decision

    def _build_graph(self):
        graph = StateGraph(SupervisorGraphState)
        graph.add_node("analyst", self._analyst_node)
        graph.add_node("researcher", self._researcher_node)
        graph.add_node("trader", self._trader_node)
        graph.add_node("risk", self._risk_node)
        graph.add_node("supervisor_finalize", self._finalize_node)
        graph.add_edge(START, "analyst")
        graph.add_edge("analyst", "researcher")
        graph.add_edge("researcher", "trader")
        graph.add_edge("trader", "risk")
        graph.add_edge("risk", "supervisor_finalize")
        graph.add_edge("supervisor_finalize", END)
        return graph.compile()

    def _analyst_node(self, state: SupervisorGraphState) -> SupervisorGraphState:
        return {
            "analyst_output": self.analyst.run(
                state["context"],
                evidence=state.get("evidence"),
            ),
            "trace": [self.analyst.name],
        }

    def _researcher_node(self, state: SupervisorGraphState) -> SupervisorGraphState:
        return {
            "researcher_output": self.researcher.run(
                state["analyst_output"],
                evidence=state.get("evidence"),
            ),
            "trace": [self.researcher.name],
        }

    def _trader_node(self, state: SupervisorGraphState) -> SupervisorGraphState:
        return {
            "trader_output": self.trader.run(
                state["analyst_output"],
                state["researcher_output"],
                evidence=state.get("evidence"),
            ),
            "trace": [self.trader.name],
        }

    def _risk_node(self, state: SupervisorGraphState) -> SupervisorGraphState:
        return {
            "risk_output": self.risk.run(
                state["context"],
                state["trader_output"],
                evidence=state.get("evidence"),
            ),
            "trace": [self.risk.name],
        }

    def _finalize_node(self, state: SupervisorGraphState) -> SupervisorGraphState:
        final_action = self._finalize(state["trader_output"].preliminary_action, state["risk_output"].approved)
        explanation = (
            f"Supervisor finalized {final_action.value} after "
            f"{state['trader_output'].preliminary_action.value} from trader and "
            f"{state['risk_output'].risk_level.value} risk review"
        )
        return {
            "final_action": final_action,
            "explanation": explanation,
            "trace": ["supervisor"],
        }

    def _finalize(self, preliminary_action: TradeAction, approved: bool) -> TradeAction:
        if approved:
            return preliminary_action
        return TradeAction.HOLD

    def run_for_symbol(
        self,
        *,
        symbol: str,
        interval: str,
        ai_engineering: AIEngineeringNode,
        lookback_candles: int = 64,
        memory_k: int = 4,
    ) -> tuple[SupervisorDecision, DecisionReport]:
        context, evidence = ai_engineering.build_context(
            symbol=symbol,
            interval=interval,
            lookback_candles=lookback_candles,
            memory_k=memory_k,
        )
        decision = self.run(context, evidence=evidence)
        report = ai_engineering.persist_decision(
            decision=decision,
            interval=interval,
            evidence=evidence,
        )
        decision.report_id = report.report_id
        return decision, report

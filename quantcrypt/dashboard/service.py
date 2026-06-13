from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Callable

from ..ai_engineering import AIEngineeringNode, DecisionReport
from ..data_foundation import DataFoundationNode, OHLCVCandle
from ..data_foundation.timeframes import INTERVAL_TO_MS
from ..models import SupervisorDecision, TradeAction
from ..observability import AlertSeverity, ComponentHealthStatus, LiveMonitor, LiveMonitorSnapshot
from ..runtime import RuntimeFactory
from ..supervisor import SupervisorNode


logger = logging.getLogger(__name__)


class DashboardMode(StrEnum):
    BACKTEST = "backtest"
    PAPER_TRADING = "paper_trading"
    LIVE_TRADING = "live_trading"


class ExecutionStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class RunConfig:
    mode: DashboardMode
    symbol: str
    interval: str
    lookback_candles: int = 64
    memory_k: int = 4
    backtest_candles: int = 50
    poll_interval_seconds: float = 15.0
    demo_account: bool = True


@dataclass(slots=True)
class BacktestResult:
    evaluation_open_time_ms: int
    next_open_time_ms: int
    final_action: str
    risk_level: str
    confidence: float
    market_return_pct: float
    strategy_return_pct: float
    approved: bool
    report_summary: str


@dataclass(slots=True)
class BacktestSummary:
    total_cycles: int
    buy_count: int
    sell_count: int
    hold_count: int
    approved_trade_count: int
    hit_rate: float
    cumulative_strategy_return_pct: float
    cumulative_market_return_pct: float
    results: list[BacktestResult]


@dataclass(slots=True)
class DashboardSnapshot:
    status: ExecutionStatus = ExecutionStatus.IDLE
    mode: DashboardMode = DashboardMode.PAPER_TRADING
    symbol: str = "BTCUSDT"
    interval: str = "1m"
    run_id: str | None = None
    demo_account: bool = True
    cycle_count: int = 0
    last_started_at: str | None = None
    last_updated_at: str | None = None
    last_completed_at: str | None = None
    last_error: str | None = None
    status_message: str = "Ready."
    stop_requested: bool = False
    latest_decision: SupervisorDecision | None = None
    latest_report: DecisionReport | None = None
    backtest_summary: BacktestSummary | None = None


@dataclass(slots=True)
class DashboardState:
    snapshot: DashboardSnapshot
    monitor_snapshot: LiveMonitorSnapshot
    available_candles: int
    latest_candle: OHLCVCandle | None
    recent_candles: list[OHLCVCandle]
    report_count: int
    memory_count: int
    recent_reports: list[DecisionReport]


@dataclass(slots=True)
class MonitorCycleResult:
    latest_candle: OHLCVCandle
    decision: SupervisorDecision
    report: DecisionReport


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def sync_recent_market_data(
    data_foundation: DataFoundationNode,
    *,
    symbol: str,
    interval: str,
    lookback_candles: int,
) -> int:
    interval_ms = INTERVAL_TO_MS.get(interval)
    if interval_ms is None:
        raise ValueError(f"Unsupported interval for dashboard sync: {interval}")

    end_time_ms = int(time.time() * 1000)
    history_span_ms = max(interval_ms * lookback_candles * 3, interval_ms * 200)
    start_time_ms = max(0, end_time_ms - history_span_ms)
    return data_foundation.backfill_rest_klines(
        symbol=symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
    )


def execute_monitor_cycle(
    *,
    data_foundation: DataFoundationNode,
    ai_engineering: AIEngineeringNode,
    supervisor: SupervisorNode,
    config: RunConfig,
    monitor: LiveMonitor | None = None,
    previous_open_time_ms: int | None = None,
    sync_data: bool = True,
) -> MonitorCycleResult | None:
    if sync_data:
        if monitor is not None:
            monitor.set_component_status(
                "data_sync",
                status=ComponentHealthStatus.RUNNING,
                message=f"Syncing recent market data for {config.symbol} {config.interval}.",
            )
        try:
            inserted_count = sync_recent_market_data(
                data_foundation,
                symbol=config.symbol,
                interval=config.interval,
                lookback_candles=config.lookback_candles,
            )
            if monitor is not None:
                monitor.set_component_status(
                    "data_sync",
                    status=ComponentHealthStatus.HEALTHY,
                    message=(
                        f"Recent market sync completed for {config.symbol} {config.interval}. "
                        f"Inserted or refreshed {inserted_count} candles."
                    ),
                )
        except Exception:
            logger.warning(
                "Failed to sync recent market data for %s %s. Falling back to existing stored candles.",
                config.symbol,
                config.interval,
                exc_info=True,
            )
            if monitor is not None:
                message = (
                    f"Failed to sync recent market data for {config.symbol} {config.interval}. "
                    "Using the existing local candle store."
                )
                monitor.set_component_status(
                    "data_sync",
                    status=ComponentHealthStatus.WARNING,
                    message=message,
                )
                monitor.record_alert(
                    severity=AlertSeverity.WARNING,
                    source="data_sync",
                    message=message,
                    details={"symbol": config.symbol, "interval": config.interval},
                )

    latest_candle = data_foundation.store.fetch_latest_candle(
        symbol=config.symbol,
        interval=config.interval,
    )
    if latest_candle is None or latest_candle.open_time_ms == previous_open_time_ms:
        return None

    decision, report = supervisor.run_for_symbol(
        symbol=config.symbol,
        interval=config.interval,
        ai_engineering=ai_engineering,
        lookback_candles=config.lookback_candles,
        memory_k=config.memory_k,
    )
    return MonitorCycleResult(
        latest_candle=latest_candle,
        decision=decision,
        report=report,
    )


def execute_backtest(
    *,
    data_foundation: DataFoundationNode,
    ai_engineering: AIEngineeringNode,
    supervisor: SupervisorNode,
    config: RunConfig,
    stop_event: threading.Event | None = None,
    progress_callback: Callable[[int, SupervisorDecision], None] | None = None,
) -> BacktestSummary:
    candles = data_foundation.load_clean_ohlcv(
        symbol=config.symbol,
        interval=config.interval,
    )
    minimum_required = config.lookback_candles + 2
    if len(candles) < minimum_required:
        raise RuntimeError(
            f"Backtest needs at least {minimum_required} candles for {config.symbol} {config.interval}, "
            f"but found {len(candles)}."
        )

    max_cycles = len(candles) - config.lookback_candles
    cycle_count = min(config.backtest_candles, max_cycles)
    evaluation_start_index = len(candles) - cycle_count - 1

    buy_count = 0
    sell_count = 0
    hold_count = 0
    approved_trade_count = 0
    winning_trade_count = 0
    trade_count = 0
    strategy_equity = 1.0
    market_equity = 1.0
    results: list[BacktestResult] = []

    for evaluation_index in range(evaluation_start_index, len(candles) - 1):
        if stop_event is not None and stop_event.is_set():
            break

        window = candles[evaluation_index - config.lookback_candles + 1 : evaluation_index + 1]
        next_candle = candles[evaluation_index + 1]
        context, evidence = ai_engineering.build_context_from_candles(
            symbol=config.symbol,
            interval=config.interval,
            candles=window,
            memory_k=config.memory_k,
            memory_before_ms=window[-1].open_time_ms,
        )
        decision = supervisor.run(context, evidence=evidence)

        market_return_pct = (next_candle.close_price / window[-1].close_price) - 1.0
        if decision.final_action == TradeAction.BUY:
            strategy_return_pct = market_return_pct
            buy_count += 1
        elif decision.final_action == TradeAction.SELL:
            strategy_return_pct = -market_return_pct
            sell_count += 1
        else:
            strategy_return_pct = 0.0
            hold_count += 1

        if decision.final_action != TradeAction.HOLD:
            trade_count += 1
            if strategy_return_pct > 0:
                winning_trade_count += 1
        if decision.risk.approved:
            approved_trade_count += 1

        strategy_equity *= 1.0 + strategy_return_pct
        market_equity *= 1.0 + market_return_pct

        results.append(
            BacktestResult(
                evaluation_open_time_ms=window[-1].open_time_ms,
                next_open_time_ms=next_candle.open_time_ms,
                final_action=decision.final_action.value,
                risk_level=decision.risk.risk_level.value,
                confidence=decision.trader.confidence,
                market_return_pct=market_return_pct,
                strategy_return_pct=strategy_return_pct,
                approved=decision.risk.approved,
                report_summary=decision.explanation,
            )
        )
        if progress_callback is not None:
            progress_callback(len(results), decision)

    hit_rate = (winning_trade_count / trade_count) if trade_count else 0.0
    return BacktestSummary(
        total_cycles=len(results),
        buy_count=buy_count,
        sell_count=sell_count,
        hold_count=hold_count,
        approved_trade_count=approved_trade_count,
        hit_rate=hit_rate,
        cumulative_strategy_return_pct=strategy_equity - 1.0,
        cumulative_market_return_pct=market_equity - 1.0,
        results=results,
    )


class DashboardController:
    def __init__(self, runtime_factory: RuntimeFactory | None = None) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot = DashboardSnapshot()
        self._runtime_factory = runtime_factory or RuntimeFactory()

    def snapshot(self) -> DashboardSnapshot:
        with self._lock:
            return replace(self._snapshot)

    def build_state(
        self,
        *,
        symbol: str,
        interval: str,
        report_limit: int = 8,
        candle_limit: int = 64,
    ) -> DashboardState:
        services = self._runtime_factory.build()
        data_foundation = services.data_foundation
        ai_engineering = services.ai_engineering
        return DashboardState(
            snapshot=self.snapshot(),
            monitor_snapshot=self._runtime_factory.monitor.snapshot(),
            available_candles=data_foundation.store.count_candles(symbol=symbol, interval=interval),
            latest_candle=data_foundation.store.fetch_latest_candle(symbol=symbol, interval=interval),
            recent_candles=data_foundation.load_latest_clean_ohlcv(
                symbol=symbol,
                interval=interval,
                limit=candle_limit,
            ),
            report_count=ai_engineering.store.count_decision_reports(),
            memory_count=ai_engineering.store.count_memory_documents(),
            recent_reports=ai_engineering.store.fetch_recent_decision_reports(
                limit=report_limit,
                symbol=symbol,
                interval=interval,
            ),
        )

    def start(self, config: RunConfig) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop_event = threading.Event()
            run_id = self._runtime_factory.monitor.start_run(
                mode=config.mode.value,
                symbol=config.symbol,
                interval=config.interval,
            )
            self._snapshot = DashboardSnapshot(
                status=ExecutionStatus.RUNNING,
                mode=config.mode,
                symbol=config.symbol,
                interval=config.interval,
                run_id=run_id,
                demo_account=config.demo_account,
                cycle_count=0,
                last_started_at=_utc_now_iso(),
                last_updated_at=_utc_now_iso(),
                status_message="Execution started.",
            )
            self._thread = threading.Thread(
                target=self._run,
                args=(config,),
                name="quantcrypt-dashboard-runner",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            if self._snapshot.status == ExecutionStatus.RUNNING:
                self._snapshot.status = ExecutionStatus.STOPPING
                self._snapshot.stop_requested = True
                self._snapshot.last_updated_at = _utc_now_iso()
                self._snapshot.status_message = "Stop requested. Waiting for the current cycle to finish."
                self._runtime_factory.monitor.set_component_status(
                    "dashboard_runner",
                    status=ComponentHealthStatus.STOPPING,
                    message="Stop requested. Waiting for the current cycle to finish.",
                )

    def _update_snapshot(self, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(self._snapshot, key, value)

    def _run(self, config: RunConfig) -> None:
        try:
            services = self._runtime_factory.build()
            data_foundation = services.data_foundation
            ai_engineering = services.ai_engineering
            supervisor = services.supervisor
            if config.mode == DashboardMode.BACKTEST:
                self._run_backtest(
                    config=config,
                    data_foundation=data_foundation,
                    ai_engineering=ai_engineering,
                    supervisor=supervisor,
                )
            else:
                self._run_monitor_mode(
                    config=config,
                    data_foundation=data_foundation,
                    ai_engineering=ai_engineering,
                    supervisor=supervisor,
                )
        except Exception as exc:
            logger.exception(
                "Dashboard execution failed for %s mode on %s %s.",
                config.mode.value,
                config.symbol,
                config.interval,
            )
            self._runtime_factory.monitor.record_alert(
                severity=AlertSeverity.CRITICAL,
                source="dashboard_runner",
                message=f"Dashboard execution failed for {config.symbol} {config.interval}: {exc}",
                details={"mode": config.mode.value},
            )
            self._runtime_factory.monitor.finish_run(
                status=ComponentHealthStatus.FAILED,
                message=f"Execution failed for {config.symbol} {config.interval}.",
            )
            self._update_snapshot(
                status=ExecutionStatus.FAILED,
                last_error=str(exc),
                last_updated_at=_utc_now_iso(),
                last_completed_at=_utc_now_iso(),
                status_message="Execution failed.",
            )

    def _run_backtest(
        self,
        *,
        config: RunConfig,
        data_foundation: DataFoundationNode,
        ai_engineering: AIEngineeringNode,
        supervisor: SupervisorNode,
    ) -> None:
        def on_progress(cycle_count: int, decision: SupervisorDecision) -> None:
            self._update_snapshot(
                cycle_count=cycle_count,
                latest_decision=decision,
                last_updated_at=_utc_now_iso(),
                status_message=f"Backtest processed {cycle_count} historical windows.",
            )

        summary = execute_backtest(
            data_foundation=data_foundation,
            ai_engineering=ai_engineering,
            supervisor=supervisor,
            config=config,
            stop_event=self._stop_event,
            progress_callback=on_progress,
        )
        final_status = ExecutionStatus.STOPPED if self._stop_event.is_set() else ExecutionStatus.COMPLETED
        self._update_snapshot(
            status=final_status,
            backtest_summary=summary,
            cycle_count=summary.total_cycles,
            stop_requested=self._stop_event.is_set(),
            last_updated_at=_utc_now_iso(),
            last_completed_at=_utc_now_iso(),
            status_message=(
                f"Backtest stopped after {summary.total_cycles} cycles."
                if self._stop_event.is_set()
                else f"Backtest completed with {summary.total_cycles} cycles."
            ),
        )
        self._runtime_factory.monitor.finish_run(
            status=ComponentHealthStatus.STOPPED if self._stop_event.is_set() else ComponentHealthStatus.COMPLETED,
            message=(
                f"Backtest stopped after {summary.total_cycles} cycles."
                if self._stop_event.is_set()
                else f"Backtest completed with {summary.total_cycles} cycles."
            ),
        )

    def _run_monitor_mode(
        self,
        *,
        config: RunConfig,
        data_foundation: DataFoundationNode,
        ai_engineering: AIEngineeringNode,
        supervisor: SupervisorNode,
    ) -> None:
        previous_open_time_ms: int | None = None
        while not self._stop_event.is_set():
            cycle_result = execute_monitor_cycle(
                data_foundation=data_foundation,
                ai_engineering=ai_engineering,
                supervisor=supervisor,
                config=config,
                monitor=self._runtime_factory.monitor,
                previous_open_time_ms=previous_open_time_ms,
            )
            if cycle_result is None:
                self._update_snapshot(
                    last_updated_at=_utc_now_iso(),
                    status_message="Waiting for a new closed candle in the database.",
                )
            else:
                previous_open_time_ms = cycle_result.latest_candle.open_time_ms
                self._update_snapshot(
                    cycle_count=self.snapshot().cycle_count + 1,
                    latest_decision=cycle_result.decision,
                    latest_report=cycle_result.report,
                    last_updated_at=_utc_now_iso(),
                    status_message=(
                        f"Processed {config.symbol} {config.interval} candle at "
                        f"{cycle_result.latest_candle.open_time_ms}."
                    ),
                )
            if self._stop_event.wait(config.poll_interval_seconds):
                break

        self._update_snapshot(
            status=ExecutionStatus.STOPPED,
            stop_requested=True,
            last_updated_at=_utc_now_iso(),
            last_completed_at=_utc_now_iso(),
            status_message=f"{config.mode.value.replace('_', ' ')} stopped.",
        )
        self._runtime_factory.monitor.finish_run(
            status=ComponentHealthStatus.STOPPED,
            message=f"{config.mode.value.replace('_', ' ')} stopped.",
        )

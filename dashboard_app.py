from __future__ import annotations

from datetime import UTC, datetime

import pandas
import streamlit as st

from quantcrypt.dashboard import DashboardController, DashboardMode, ExecutionStatus, RunConfig


MODE_LABELS = {
    DashboardMode.BACKTEST: "Backtest",
    DashboardMode.PAPER_TRADING: "Paper Trading",
    DashboardMode.LIVE_TRADING: "Live Trading",
}


@st.cache_resource
def get_dashboard_controller() -> DashboardController:
    return DashboardController()


def _format_timestamp(timestamp_ms: int | None) -> str:
    if timestamp_ms is None:
        return "n/a"
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _render_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

        html, body, [class*="css"]  {
            font-family: "Space Grotesk", "Segoe UI", sans-serif;
        }

        [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at top left, rgba(57, 144, 255, 0.22), transparent 32%),
                radial-gradient(circle at top right, rgba(33, 191, 115, 0.18), transparent 28%),
                linear-gradient(180deg, #07111f 0%, #0d1627 48%, #121924 100%);
        }

        [data-testid="stHeader"] {
            background: rgba(0, 0, 0, 0);
        }

        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1380px;
        }

        .qc-hero {
            border: 1px solid rgba(109, 170, 255, 0.24);
            border-radius: 24px;
            padding: 1.4rem 1.5rem 1.2rem 1.5rem;
            background: linear-gradient(135deg, rgba(9, 18, 36, 0.88), rgba(18, 31, 54, 0.82));
            box-shadow: 0 18px 60px rgba(0, 0, 0, 0.22);
            margin-bottom: 1rem;
        }

        .qc-kicker {
            color: #7ec8ff;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }

        .qc-title {
            color: #f5fbff;
            font-size: 2.5rem;
            font-weight: 700;
            line-height: 1.05;
            margin: 0;
        }

        .qc-subtitle {
            color: #b7c7db;
            font-size: 1rem;
            margin-top: 0.65rem;
            max-width: 58rem;
        }

        .qc-note {
            color: #9fe7bf;
            font-size: 0.88rem;
            margin-top: 0.9rem;
            font-family: "IBM Plex Mono", monospace;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _report_rows(reports) -> list[dict[str, object]]:
    return [
        {
            "created_at": _format_timestamp(report.created_at_ms),
            "report_id": report.report_id,
            "action": report.final_action,
            "risk": report.risk_level,
            "memories": report.retrieved_memory_count,
            "summary": report.report_summary,
        }
        for report in reports
    ]


def _backtest_rows(summary) -> list[dict[str, object]]:
    if summary is None:
        return []
    return [
        {
            "evaluation_time": _format_timestamp(result.evaluation_open_time_ms),
            "next_time": _format_timestamp(result.next_open_time_ms),
            "action": result.final_action,
            "position_state": result.position_state,
            "risk": result.risk_level,
            "confidence": round(result.confidence, 3),
            "market_return_pct": round(result.market_return_pct * 100.0, 3),
            "strategy_return_pct": round(result.strategy_return_pct * 100.0, 3),
            "approved": result.approved,
            "summary": result.report_summary,
        }
        for result in summary.results
    ]


def _component_rows(component_statuses) -> list[dict[str, object]]:
    return [
        {
            "component": entry.component_name,
            "status": entry.status,
            "updated_at": _format_timestamp(entry.updated_at_ms),
            "message": entry.message,
        }
        for entry in component_statuses
    ]


def _alert_rows(alerts) -> list[dict[str, object]]:
    return [
        {
            "time": _format_timestamp(alert.timestamp_ms),
            "severity": alert.severity,
            "source": alert.source,
            "message": alert.message,
            "details": alert.details,
        }
        for alert in alerts
    ]


def _agent_log_rows(agent_logs) -> list[dict[str, object]]:
    return [
        {
            "time": _format_timestamp(entry.timestamp_ms),
            "run_id": entry.run_id or "n/a",
            "agent": entry.agent_name,
            "phase": entry.phase,
            "message": entry.message,
            "metadata": entry.metadata,
        }
        for entry in agent_logs
    ]


def _find_component_status(component_statuses, component_name: str) -> str:
    for entry in component_statuses:
        if entry.component_name == component_name:
            return entry.status
    return "n/a"


def _render_dashboard_state(
    *,
    controller: DashboardController,
    symbol: str,
    interval: str,
) -> None:
    state = controller.build_state(symbol=symbol, interval=interval)
    snapshot = state.snapshot
    monitor_snapshot = state.monitor_snapshot
    critical_alerts = [alert for alert in monitor_snapshot.alerts if alert.severity == "critical"]

    for alert in critical_alerts[:2]:
        st.error(f"{alert.source}: {alert.message}")

    if snapshot.status == ExecutionStatus.FAILED and snapshot.last_error:
        st.error(snapshot.last_error)
    elif snapshot.status == ExecutionStatus.STOPPING:
        st.warning(snapshot.status_message)
    elif snapshot.status == ExecutionStatus.RUNNING:
        st.info(snapshot.status_message)
    elif snapshot.status == ExecutionStatus.COMPLETED:
        st.success(snapshot.status_message)
    elif snapshot.status == ExecutionStatus.STOPPED:
        st.warning(snapshot.status_message)
    else:
        st.caption(snapshot.status_message)

    metric_columns = st.columns(8)
    metric_columns[0].metric("Runner Status", snapshot.status.value.replace("_", " ").title())
    metric_columns[1].metric("LLM Status", _find_component_status(monitor_snapshot.component_statuses, "ollama").upper())
    metric_columns[2].metric("Critical Alerts", len(critical_alerts))
    metric_columns[3].metric("Cycles", snapshot.cycle_count)
    metric_columns[4].metric("Candles", state.available_candles)
    metric_columns[5].metric("Reports", state.report_count)
    metric_columns[6].metric("Memories", state.memory_count)
    metric_columns[7].metric(
        "Latest Close",
        f"{state.latest_candle.close_price:.4f}" if state.latest_candle is not None else "n/a",
    )

    execution_tab, monitor_tab, backtest_tab, reports_tab, data_tab = st.tabs(
        ["Execution", "Live Monitor", "Backtest", "Reports", "Data Foundation"]
    )

    with execution_tab:
        st.subheader("Run State")
        state_rows = [
            {"field": "Mode", "value": MODE_LABELS[snapshot.mode]},
            {"field": "Symbol", "value": snapshot.symbol},
            {"field": "Interval", "value": snapshot.interval},
            {"field": "Demo Account", "value": "Yes" if snapshot.demo_account else "No"},
            {"field": "Started", "value": snapshot.last_started_at or "n/a"},
            {"field": "Updated", "value": snapshot.last_updated_at or "n/a"},
            {"field": "Completed", "value": snapshot.last_completed_at or "n/a"},
        ]
        st.dataframe(pandas.DataFrame(state_rows), width="stretch", hide_index=True)

        st.subheader("Trading Scope")
        scope_rows = [
            {"field": "Exchange", "value": state.trading_scope.exchange.title()},
            {"field": "Asset Class", "value": state.trading_scope.asset_class.title()},
            {"field": "Market Type", "value": state.trading_scope.market_type.title()},
            {"field": "Monitored Symbol", "value": state.trading_scope.monitored_symbol},
            {"field": "Strategy Style", "value": state.trading_scope.strategy_style},
            {"field": "Actions", "value": ", ".join(action.upper() for action in state.trading_scope.allowed_actions)},
            {"field": "SELL Meaning", "value": state.trading_scope.sell_behavior},
            {"field": "Shorting", "value": "Supported" if state.trading_scope.supports_shorting else "Not supported"},
            {
                "field": "Order Routing",
                "value": "Exchange order routing enabled"
                if state.trading_scope.routes_exchange_orders
                else "No exchange orders. Signal and demo mode only.",
            },
            {"field": "Market Orders", "value": "Implemented" if state.trading_scope.uses_market_orders else "Not implemented"},
            {"field": "Limit Orders", "value": "Implemented" if state.trading_scope.uses_limit_orders else "Not implemented"},
            {"field": "Stop Loss", "value": "Implemented" if state.trading_scope.uses_stop_loss else "Not implemented"},
            {"field": "Take Profit", "value": "Implemented" if state.trading_scope.uses_take_profit else "Not implemented"},
        ]
        st.dataframe(pandas.DataFrame(scope_rows), width="stretch", hide_index=True)
        st.caption("This is a crypto-only Binance spot strategy in the current build. Stock trading is not supported.")

        if snapshot.latest_decision is not None:
            st.subheader("Latest Supervisor Decision")
            decision_cols = st.columns(4)
            decision_cols[0].metric("Final Action", snapshot.latest_decision.final_action.value.upper())
            decision_cols[1].metric("Risk", snapshot.latest_decision.risk.risk_level.value.upper())
            decision_cols[2].metric("Trader Confidence", f"{snapshot.latest_decision.trader.confidence:.2f}")
            decision_cols[3].metric("Retrieved Memories", snapshot.latest_decision.retrieved_memory_count)
            st.write(snapshot.latest_decision.explanation)
            st.code(" -> ".join(snapshot.latest_decision.trace), language="text")

        if snapshot.latest_report is not None:
            st.subheader("Latest Persisted Report")
            st.write(snapshot.latest_report.report_summary)
            for agent_report in snapshot.latest_report.agent_reports:
                with st.expander(agent_report.agent_name.title(), expanded=False):
                    st.write(agent_report.output_summary)
                    st.json(agent_report.payload)

    with monitor_tab:
        st.subheader("Component Health")
        st.dataframe(
            pandas.DataFrame(_component_rows(monitor_snapshot.component_statuses)),
            width="stretch",
            hide_index=True,
        )

        st.subheader("Active Agent Activity")
        active_components = [
            entry
            for entry in monitor_snapshot.component_statuses
            if entry.status == "running" and entry.component_name in {"supervisor", "analyst", "researcher", "trader", "risk"}
        ]
        if not active_components:
            st.caption("No agent is actively evaluating at the moment.")
        else:
            st.dataframe(
                pandas.DataFrame(_component_rows(active_components)),
                width="stretch",
                hide_index=True,
            )

        st.subheader("Alerts")
        if not monitor_snapshot.alerts:
            st.caption("No alerts recorded yet.")
        else:
            st.dataframe(
                pandas.DataFrame(_alert_rows(monitor_snapshot.alerts)),
                width="stretch",
                hide_index=True,
            )

        st.subheader("Agent Activity Stream")
        if not monitor_snapshot.agent_logs:
            st.caption("No agent activity recorded yet.")
        else:
            st.dataframe(
                pandas.DataFrame(_agent_log_rows(monitor_snapshot.agent_logs)),
                width="stretch",
                hide_index=True,
            )

    with backtest_tab:
        st.subheader("Backtest Summary")
        if snapshot.backtest_summary is None:
            st.caption("Run Backtest mode to generate a historical signal summary.")
        else:
            summary = snapshot.backtest_summary
            backtest_metrics = st.columns(6)
            backtest_metrics[0].metric("Cycles", summary.total_cycles)
            backtest_metrics[1].metric("Buy", summary.buy_count)
            backtest_metrics[2].metric("Sell", summary.sell_count)
            backtest_metrics[3].metric("Hold", summary.hold_count)
            backtest_metrics[4].metric("Hit Rate", f"{summary.hit_rate:.1%}")
            backtest_metrics[5].metric(
                "Strategy Return",
                f"{summary.cumulative_strategy_return_pct:.2%}",
                delta=f"Market {summary.cumulative_market_return_pct:.2%}",
            )
            rows = _backtest_rows(summary)
            if rows:
                st.dataframe(pandas.DataFrame(rows), width="stretch", hide_index=True)

    with reports_tab:
        st.subheader("Recent Persisted Reports")
        if not state.recent_reports:
            st.caption("No persisted paper or live demo reports yet for this symbol and interval.")
        else:
            st.dataframe(pandas.DataFrame(_report_rows(state.recent_reports)), width="stretch", hide_index=True)

    with data_tab:
        st.subheader("Data Foundation Status")
        if state.latest_candle is None:
            st.warning("No candles are stored yet for this symbol and interval.")
        else:
            latest_candle_rows = [
                {"field": "Exchange", "value": state.latest_candle.exchange},
                {"field": "Market Type", "value": state.latest_candle.market_type},
                {"field": "Symbol", "value": state.latest_candle.symbol},
                {"field": "Open Time", "value": _format_timestamp(state.latest_candle.open_time_ms)},
                {"field": "Close Time", "value": _format_timestamp(state.latest_candle.close_time_ms)},
                {"field": "Open", "value": state.latest_candle.open_price},
                {"field": "High", "value": state.latest_candle.high_price},
                {"field": "Low", "value": state.latest_candle.low_price},
                {"field": "Close", "value": state.latest_candle.close_price},
                {"field": "Volume", "value": state.latest_candle.volume},
                {"field": "Source", "value": state.latest_candle.source},
            ]
            st.dataframe(pandas.DataFrame(latest_candle_rows), width="stretch", hide_index=True)

        if state.recent_candles:
            chart_frame = pandas.DataFrame(
                {
                    "timestamp": [_format_timestamp(candle.open_time_ms) for candle in state.recent_candles],
                    "close": [candle.close_price for candle in state.recent_candles],
                    "volume": [candle.volume for candle in state.recent_candles],
                }
            ).set_index("timestamp")
            st.line_chart(chart_frame[["close"]], width="stretch")
            st.bar_chart(chart_frame[["volume"]], width="stretch")


def main() -> None:
    st.set_page_config(
        page_title="QuantCrypt Dashboard",
        page_icon="QC",
        layout="wide",
    )
    _render_styles()

    controller = get_dashboard_controller()

    st.markdown(
        """
        <div class="qc-hero">
            <div class="qc-kicker">QuantCrypt Control Deck</div>
            <h1 class="qc-title">Supervisor-driven crypto agent dashboard</h1>
            <div class="qc-subtitle">
                Backtest historical signals, run paper trading loops, and stage live trading in demo mode on top of the current
                Data Foundation, AI Engineering, and Supervisor architecture.
            </div>
            <div class="qc-note">Live Trading remains demo-account only in the current system. No exchange orders are placed from this dashboard.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.header("Execution Config")
    mode = DashboardMode(
        st.sidebar.radio(
            "Mode",
            options=[mode.value for mode in DashboardMode],
            format_func=lambda value: MODE_LABELS[DashboardMode(value)],
        )
    )
    symbol = st.sidebar.text_input("Symbol", value="BTCUSDT").strip().upper() or "BTCUSDT"
    interval = st.sidebar.selectbox("Interval", options=["1m", "5m", "15m", "1h", "4h", "1d"], index=0)
    lookback_candles = int(st.sidebar.slider("Lookback Candles", min_value=16, max_value=256, value=64, step=8))
    memory_k = int(st.sidebar.slider("Memory Retrieval", min_value=0, max_value=8, value=4, step=1))
    backtest_candles = int(st.sidebar.number_input("Backtest Cycles", min_value=10, max_value=500, value=50, step=10))
    poll_interval_seconds = float(
        st.sidebar.number_input("Run Poll Seconds", min_value=5.0, max_value=300.0, value=15.0, step=5.0)
    )
    auto_refresh_enabled = st.sidebar.toggle("Auto Refresh", value=True)
    auto_refresh_seconds = float(
        st.sidebar.slider("Refresh Seconds", min_value=1.0, max_value=10.0, value=2.0, step=0.5)
    )
    st.sidebar.caption("Paper Trading and Live Trading both use demo execution in the current build.")
    st.sidebar.caption("The current build monitors one symbol per active run, using Binance spot market data only.")

    config = RunConfig(
        mode=mode,
        symbol=symbol,
        interval=interval,
        lookback_candles=lookback_candles,
        memory_k=memory_k,
        backtest_candles=backtest_candles,
        poll_interval_seconds=poll_interval_seconds,
        demo_account=True,
    )

    action_col, stop_col, refresh_col, mode_col = st.columns([1, 1, 1, 2])
    with action_col:
        run_clicked = st.button("Run", type="primary", width="stretch")
    with stop_col:
        stop_clicked = st.button("Stop", width="stretch")
    with refresh_col:
        refresh_clicked = st.button("Refresh", width="stretch")
    with mode_col:
        refresh_mode = "Live" if auto_refresh_enabled else "Manual"
        st.markdown(f"**Mode:** `{MODE_LABELS[mode]}`  \n**Refresh:** `{refresh_mode}`")

    if run_clicked:
        if controller.start(config):
            st.success(f"{MODE_LABELS[mode]} started.")
        else:
            st.warning("A run is already active. Stop it before starting a new one.")
    if stop_clicked:
        controller.stop()
        st.info("Stop requested.")
    if refresh_clicked:
        st.rerun()

    refresh_interval = f"{auto_refresh_seconds}s" if auto_refresh_enabled else None

    @st.fragment(run_every=refresh_interval)
    def render_live_dashboard() -> None:
        _render_dashboard_state(
            controller=controller,
            symbol=symbol,
            interval=interval,
        )

    render_live_dashboard()


if __name__ == "__main__":
    main()

from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from main import build_engine
from models import RiskSettings, StopLossMethod, TradingMode

st.set_page_config(page_title="MT5 AI Trader", layout="wide")


@st.cache_resource
def get_engine():
    engine = build_engine()
    if not engine.mt5.initialize():
        st.error("Failed to connect to MT5. Check terminal, login, and .env.")
    return engine


def draw_mode_banner(mode: TradingMode) -> None:
    if mode == TradingMode.FULL_AUTO:
        st.error("FULL_AUTO is active. Orders may be sent automatically if risk rules pass.")
    elif mode == TradingMode.SEMI_AUTO:
        st.warning("SEMI_AUTO is active. Trades require manual approval.")
    else:
        st.info("SIGNAL_ONLY is active. No orders will be sent.")


def sidebar_settings(current: RiskSettings) -> RiskSettings:
    st.sidebar.header("Risk Settings")

    symbol = st.sidebar.text_input("Symbol", value=current.symbol)
    timeframe = st.sidebar.selectbox("Timeframe", ["M1", "M5", "M15", "M30", "H1", "H4", "D1"], index=["M1", "M5", "M15", "M30", "H1", "H4", "D1"].index(current.timeframe) if current.timeframe in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"] else 2)

    mode = st.sidebar.selectbox(
        "Mode",
        [m.value for m in TradingMode],
        index=[m.value for m in TradingMode].index(current.mode.value),
    )
    analyze_on_new_candle_only = st.sidebar.checkbox(
        "Analyze only on new candle close",
        value=current.analyze_on_new_candle_only,
        help="Recommended for FULL_AUTO to reduce noise and API calls.",
    )
    trading_enabled = st.sidebar.checkbox("Trading enabled", value=current.trading_enabled)

    max_risk_per_trade_pct = st.sidebar.number_input("Max risk per trade (%)", min_value=0.1, max_value=5.0, value=float(current.max_risk_per_trade_pct), step=0.1)
    max_daily_loss_pct = st.sidebar.number_input("Max daily loss (%)", min_value=0.1, max_value=20.0, value=float(current.max_daily_loss_pct), step=0.1)
    max_trades_per_day = st.sidebar.number_input("Max trades/day", min_value=1, max_value=100, value=int(current.max_trades_per_day), step=1)
    max_open_positions = st.sidebar.number_input("Max open positions", min_value=0, max_value=50, value=int(current.max_open_positions), step=1)
    min_confidence = st.sidebar.slider("Min AI confidence", min_value=0.0, max_value=1.0, value=float(current.min_confidence), step=0.01)

    stop_loss_method = st.sidebar.selectbox(
        "Stop loss method",
        [StopLossMethod.FIXED_PIPS.value, StopLossMethod.ATR_BASED.value],
        index=0 if current.stop_loss_method == StopLossMethod.FIXED_PIPS else 1,
    )

    fixed_stop_loss_pips = st.sidebar.number_input(
        "Fixed stop loss pips",
        min_value=0.1,
        max_value=2000.0,
        value=float(current.fixed_stop_loss_pips),
        step=0.1,
    )
    atr_multiplier = st.sidebar.number_input(
        "ATR multiplier",
        min_value=0.1,
        max_value=20.0,
        value=float(current.atr_multiplier),
        step=0.1,
    )
    take_profit_rr = st.sidebar.number_input(
        "Take profit RR",
        min_value=0.1,
        max_value=20.0,
        value=float(current.take_profit_rr),
        step=0.1,
    )
    max_spread_points = st.sidebar.number_input(
        "Max spread points",
        min_value=1.0,
        max_value=10000.0,
        value=float(current.max_spread_points),
        step=1.0,
    )

    return RiskSettings(
        symbol=symbol,
        timeframe=timeframe,
        max_risk_per_trade_pct=max_risk_per_trade_pct,
        max_daily_loss_pct=max_daily_loss_pct,
        max_trades_per_day=int(max_trades_per_day),
        max_open_positions=int(max_open_positions),
        min_confidence=min_confidence,
        stop_loss_method=StopLossMethod(stop_loss_method),
        fixed_stop_loss_pips=fixed_stop_loss_pips,
        atr_multiplier=atr_multiplier,
        take_profit_rr=take_profit_rr,
        max_spread_points=max_spread_points,
        analyze_on_new_candle_only=analyze_on_new_candle_only,
        trading_enabled=trading_enabled,
        mode=TradingMode(mode),
    )


def main() -> None:
    st.title("MT5 AI Trader")
    st.caption("OpenAI as analyst. Python risk engine always controls order permission.")

    engine = get_engine()
    settings = sidebar_settings(engine.settings)
    engine.set_settings(settings)

    draw_mode_banner(settings.mode)

    st.sidebar.header("Automation")
    ui_auto_run = st.sidebar.checkbox(
        "UI auto-run (FULL_AUTO)",
        value=True,
        help="Automatically trigger cycles from UI. Backend still enforces risk rules.",
    )
    ui_auto_interval = st.sidebar.number_input(
        "UI auto-run interval (seconds)",
        min_value=5,
        max_value=300,
        value=15,
        step=1,
    )

    if settings.mode == TradingMode.FULL_AUTO and ui_auto_run:
        refresh_count = st_autorefresh(
            interval=int(ui_auto_interval) * 1000,
            key="full_auto_refresh",
        )
        last_handled_count = st.session_state.get("last_auto_refresh_count", -1)
        if refresh_count != last_handled_count:
            st.session_state["last_auto_refresh_count"] = refresh_count
            try:
                auto_result = engine.run_automatic_cycle()
                if auto_result is not None:
                    st.success(
                        "Auto cycle: "
                        f"{auto_result.signal.action.value} "
                        f"(conf {auto_result.signal.confidence:.2f})"
                    )
                else:
                    st.caption("Auto cycle: waiting for next closed candle")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Auto cycle failed: {exc}")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Analyze now", type="primary"):
            try:
                result = engine.analyze_once()
                st.success(
                    f"Signal: {result.signal.action.value} (confidence {result.signal.confidence:.2f})"
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Analyze failed: {exc}")

    with c2:
        if st.button("Emergency stop ON"):
            engine.set_emergency_stop(True)
            st.warning("Emergency stop enabled")

    with c3:
        if st.button("Emergency stop OFF"):
            engine.set_emergency_stop(False)
            st.info("Emergency stop disabled")

    if engine.state.pending_proposal is not None:
        st.subheader("Pending Trade Proposal")
        p = engine.state.pending_proposal
        st.json(p.model_dump(mode="json"))
        if st.button("Approve trade"):
            resp = engine.approve_pending_trade()
            if resp.get("ok"):
                st.success("Trade sent")
            else:
                st.error(f"Approval failed: {resp}")

    st.subheader("Runtime status")
    st.write(
        {
            "emergency_stop": engine.state.emergency_stop,
            "mode": settings.mode.value,
            "analyze_on_new_candle_only": settings.analyze_on_new_candle_only,
            "trading_enabled": settings.trading_enabled,
        }
    )

    account = engine.mt5.get_account_snapshot()
    positions = engine.mt5.get_positions(symbol=settings.symbol)

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Balance", f"{account.balance:.2f}")
    a2.metric("Equity", f"{account.equity:.2f}")
    a3.metric("Daily P/L", f"{account.daily_pl:.2f}")
    a4.metric("Open Positions", str(len(positions)))

    st.subheader("Open positions")
    if positions:
        st.dataframe(pd.DataFrame([p.model_dump(mode="json") for p in positions]))
    else:
        st.info("No open positions")

    st.subheader("Last cycle")
    if engine.state.last_result is not None:
        st.json(engine.state.last_result.model_dump(mode="json"))
    else:
        st.info("No cycle run yet")

    st.subheader("Recent logs")
    logs = engine.logger.tail(limit=150)
    if logs:
        st.dataframe(pd.DataFrame(logs[::-1]))
    else:
        st.info("No logs yet")


if __name__ == "__main__":
    main()

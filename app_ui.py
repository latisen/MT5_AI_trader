from __future__ import annotations

import calendar
from datetime import UTC, datetime

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from market_hours import format_countdown, get_market_clock
from main import build_engine
from models import RiskSettings, StopLossMethod, TradingMode

st.set_page_config(page_title="MT5 AI Trader", layout="wide")

WEEKDAYS = [
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
]

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


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

    st.sidebar.header("Market Hours (UTC)")
    market_hours_enabled = st.sidebar.checkbox(
        "Pause when market is closed",
        value=current.market_hours_enabled,
    )
    market_open_day = st.sidebar.selectbox(
        "Market opens day",
        WEEKDAYS,
        index=WEEKDAYS.index(current.market_open_day) if current.market_open_day in WEEKDAYS else 6,
    )
    market_open_time_utc = st.sidebar.text_input(
        "Market opens time (UTC, HH:MM)",
        value=current.market_open_time_utc,
    )
    market_close_day = st.sidebar.selectbox(
        "Market closes day",
        WEEKDAYS,
        index=WEEKDAYS.index(current.market_close_day) if current.market_close_day in WEEKDAYS else 4,
    )
    market_close_time_utc = st.sidebar.text_input(
        "Market closes time (UTC, HH:MM)",
        value=current.market_close_time_utc,
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
        market_hours_enabled=market_hours_enabled,
        market_open_day=market_open_day,
        market_open_time_utc=market_open_time_utc,
        market_close_day=market_close_day,
        market_close_time_utc=market_close_time_utc,
        trading_enabled=trading_enabled,
        mode=TradingMode(mode),
    )


def draw_market_clock(settings: RiskSettings) -> None:
    clock = get_market_clock(settings)
    status_text = "OPEN" if clock.is_open else "CLOSED"
    countdown = format_countdown(clock.seconds_to_next_event)
    next_label = "closes" if clock.next_event_type == "CLOSE" else "opens"

    left, right = st.columns([2, 3])
    with left:
        if clock.is_open:
            st.success(f"Market status: {status_text}")
        else:
            st.warning(f"Market status: {status_text}")
    with right:
        st.info(
            f"Current UTC: {clock.now_utc.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"Next {next_label}: {clock.next_event_at_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC | "
            f"Countdown: {countdown}"
        )


def _calendar_tile_style(value: float | None) -> str:
    if value is None:
        return "background:#f3f4f8;color:#8b90a0;"
    if value > 0:
        return "background:#d8f7df;color:#0b6b2f;border:1px solid #7ed692;"
    if value < 0:
        return "background:#ffe0e0;color:#8d1c1c;border:1px solid #f2a3a3;"
    return "background:#f7f7f7;color:#5e6373;border:1px solid #dde1eb;"


def draw_pnl_calendar(engine, symbol: str) -> None:
    st.subheader("P/L Calendar")

    now_utc = datetime.now(UTC)
    if "calendar_year" not in st.session_state or "calendar_month" not in st.session_state:
        st.session_state["calendar_year"] = now_utc.year
        st.session_state["calendar_month"] = now_utc.month

    nav1, nav2, nav3, nav4 = st.columns([1, 1, 1, 3])
    with nav1:
        if st.button("<- Prev month", key="prev_month"):
            month = int(st.session_state["calendar_month"]) - 1
            year = int(st.session_state["calendar_year"])
            if month == 0:
                month = 12
                year -= 1
            st.session_state["calendar_year"] = year
            st.session_state["calendar_month"] = month
    with nav2:
        if st.button("This month", key="current_month"):
            st.session_state["calendar_year"] = now_utc.year
            st.session_state["calendar_month"] = now_utc.month
    with nav3:
        if st.button("Next month ->", key="next_month"):
            month = int(st.session_state["calendar_month"]) + 1
            year = int(st.session_state["calendar_year"])
            if month == 13:
                month = 1
                year += 1
            st.session_state["calendar_year"] = year
            st.session_state["calendar_month"] = month

    year = int(st.session_state["calendar_year"])
    month = int(st.session_state["calendar_month"])

    month_name = calendar.month_name[month]
    st.markdown(f"### {month_name} {year}")

    daily = engine.mt5.get_daily_closed_pl(year=year, month=month, symbol=symbol)

    net = sum(daily.values()) if daily else 0.0
    win_days = sum(1 for v in daily.values() if v > 0)
    loss_days = sum(1 for v in daily.values() if v < 0)
    active_days = len(daily)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Month Net P/L", f"{net:.2f}")
    m2.metric("Winning Days", str(win_days))
    m3.metric("Losing Days", str(loss_days))
    m4.metric("Active Days", str(active_days))

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    html = []
    html.append(
        "<style>"
        ".pnl-cal-grid{display:grid;grid-template-columns:repeat(7,minmax(88px,1fr));gap:8px;margin-top:8px;}"
        ".pnl-cal-head{font-weight:600;text-align:center;color:#3a3f4a;padding:6px 0;}"
        ".pnl-cal-day{border-radius:12px;padding:8px;min-height:76px;display:flex;flex-direction:column;justify-content:space-between;box-shadow:0 1px 2px rgba(23,26,32,.08);}"
        ".pnl-cal-date{font-size:12px;font-weight:700;}"
        ".pnl-cal-value{font-size:13px;font-weight:700;}"
        "</style>"
    )
    html.append("<div class='pnl-cal-grid'>")
    for label in WEEKDAY_LABELS:
        html.append(f"<div class='pnl-cal-head'>{label}</div>")

    for week in weeks:
        for day in week:
            if day == 0:
                html.append("<div class='pnl-cal-day' style='background:#f9fafc;border:1px solid #eef1f7;'></div>")
                continue
            key = f"{year:04d}-{month:02d}-{day:02d}"
            value = daily.get(key)
            style = _calendar_tile_style(value)
            value_label = "-" if value is None else f"{value:+.2f}"
            html.append(
                "<div class='pnl-cal-day' style='" + style + "'>"
                f"<div class='pnl-cal-date'>{day}</div>"
                f"<div class='pnl-cal-value'>{value_label}</div>"
                "</div>"
            )
    html.append("</div>")

    st.markdown("".join(html), unsafe_allow_html=True)


def main() -> None:
    st.title("MT5 AI Trader")
    st.caption("OpenAI as analyst. Python risk engine always controls order permission.")

    engine = get_engine()
    settings = sidebar_settings(engine.settings)
    engine.set_settings(settings)

    draw_mode_banner(settings.mode)
    draw_market_clock(settings)

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
                    if engine.state.market_paused:
                        st.caption("Auto cycle paused: market is closed")
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
            "market_hours_enabled": settings.market_hours_enabled,
            "market_paused": engine.state.market_paused,
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

    draw_pnl_calendar(engine=engine, symbol=settings.symbol)


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from models import RiskSettings, StopLossMethod, TradingMode


@dataclass
class MT5Credentials:
    login: int
    password: str
    server: str
    terminal_path: str | None = None


@dataclass
class AppConfig:
    mt5: MT5Credentials
    openai_api_key: str
    openai_model: str
    ai_timeout_seconds: int
    loop_seconds: int
    log_dir: Path
    risk_settings: RiskSettings


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    value = value.strip().lower()
    return value in {"1", "true", "yes", "on"}


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def _as_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw)


def load_config(env_file: str = ".env") -> AppConfig:
    load_dotenv(env_file)

    mt5_login = int(os.getenv("MT5_LOGIN", "0"))
    mt5_password = os.getenv("MT5_PASSWORD", "")
    mt5_server = os.getenv("MT5_SERVER", "")
    mt5_path = os.getenv("MT5_PATH")

    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    risk_settings = RiskSettings(
        symbol=os.getenv("BOT_SYMBOL", "EURUSD"),
        timeframe=os.getenv("BOT_TIMEFRAME", "M15"),
        max_spread_points=_as_float("MAX_SPREAD_POINTS", 30.0),
        trading_enabled=_as_bool(os.getenv("TRADING_ENABLED"), default=False),
        mode=TradingMode(os.getenv("BOT_MODE", TradingMode.SIGNAL_ONLY.value).upper()),
    )

    for key in (
        "MAX_RISK_PER_TRADE_PCT",
        "MAX_DAILY_LOSS_PCT",
        "MAX_TRADES_PER_DAY",
        "MAX_OPEN_POSITIONS",
        "MIN_CONFIDENCE",
        "STOP_LOSS_METHOD",
        "FIXED_STOP_LOSS_PIPS",
        "ATR_MULTIPLIER",
        "TAKE_PROFIT_RR",
    ):
        # Optional override support from environment if present.
        raw = os.getenv(key)
        if raw is None:
            continue
        if key == "MAX_RISK_PER_TRADE_PCT":
            risk_settings.max_risk_per_trade_pct = float(raw)
        elif key == "MAX_DAILY_LOSS_PCT":
            risk_settings.max_daily_loss_pct = float(raw)
        elif key == "MAX_TRADES_PER_DAY":
            risk_settings.max_trades_per_day = int(raw)
        elif key == "MAX_OPEN_POSITIONS":
            risk_settings.max_open_positions = int(raw)
        elif key == "MIN_CONFIDENCE":
            risk_settings.min_confidence = float(raw)
        elif key == "STOP_LOSS_METHOD":
            risk_settings.stop_loss_method = StopLossMethod(raw.strip().upper())
        elif key == "FIXED_STOP_LOSS_PIPS":
            risk_settings.fixed_stop_loss_pips = float(raw)
        elif key == "ATR_MULTIPLIER":
            risk_settings.atr_multiplier = float(raw)
        elif key == "TAKE_PROFIT_RR":
            risk_settings.take_profit_rr = float(raw)

    return AppConfig(
        mt5=MT5Credentials(
            login=mt5_login,
            password=mt5_password,
            server=mt5_server,
            terminal_path=mt5_path,
        ),
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        ai_timeout_seconds=_as_int("AI_TIMEOUT_SECONDS", 20),
        loop_seconds=_as_int("LOOP_SECONDS", 30),
        log_dir=Path(os.getenv("LOG_DIR", "logs")),
        risk_settings=risk_settings,
    )

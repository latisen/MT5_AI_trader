from __future__ import annotations

import time

from config import AppConfig, load_config
from mt5_client import MT5Client
from openai_signal import OpenAISignalEngine
from risk_manager import RiskManager
from trade_executor import JsonlLogger, TradingEngine


def build_engine(config: AppConfig | None = None) -> TradingEngine:
    cfg = config or load_config()

    mt5 = MT5Client(
        login=cfg.mt5.login,
        password=cfg.mt5.password,
        server=cfg.mt5.server,
        terminal_path=cfg.mt5.terminal_path,
    )

    logger = JsonlLogger(cfg.log_dir)
    signal_engine = OpenAISignalEngine(
        api_key=cfg.openai_api_key,
        model=cfg.openai_model,
        timeout_seconds=cfg.ai_timeout_seconds,
        logger=logger.append,
    )

    engine = TradingEngine(
        mt5=mt5,
        signal_engine=signal_engine,
        risk_manager=RiskManager(),
        settings=cfg.risk_settings,
        logger=logger,
    )
    return engine


def run_cli() -> None:
    cfg = load_config()
    engine = build_engine(cfg)

    if not engine.mt5.initialize():
        raise RuntimeError("Failed to initialize/login MetaTrader5 terminal")

    print("MT5 AI Trader started. Press Ctrl+C to stop.")
    print(f"Mode: {engine.settings.mode.value}, trading_enabled={engine.settings.trading_enabled}")

    try:
        while True:
            result = engine.analyze_once()
            print(
                f"[{result.timestamp.isoformat()}] action={result.signal.action.value} "
                f"conf={result.signal.confidence:.2f} allowed={result.risk_decision.allowed}"
            )
            time.sleep(cfg.loop_seconds)
    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        engine.mt5.shutdown()


if __name__ == "__main__":
    run_cli()

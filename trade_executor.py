from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models import CycleResult, RiskSettings, SignalAction, TradeProposal, TradingMode
from mt5_client import MT5Client, OrderRequest
from openai_signal import OpenAISignalEngine
from risk_manager import RiskManager
from strategy_features import compact_feature_payload, compute_features


class JsonlLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.log_dir / "events.jsonl"

    def append(self, event: str, payload: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "payload": payload,
        }
        with self.file_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")

    def tail(self, limit: int = 200) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []
        lines = self.file_path.read_text(encoding="utf-8").splitlines()
        selected = lines[-limit:]
        out: list[dict[str, Any]] = []
        for line in selected:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def count_event_today(self, event: str) -> int:
        today_prefix = datetime.now(UTC).date().isoformat()
        count = 0
        for row in self.tail(limit=5000):
            ts = str(row.get("ts", ""))
            if ts.startswith(today_prefix) and row.get("event") == event:
                count += 1
        return count


@dataclass
class TradingEngineState:
    emergency_stop: bool = False
    pending_proposal: TradeProposal | None = None
    last_result: CycleResult | None = None


class TradingEngine:
    def __init__(
        self,
        mt5: MT5Client,
        signal_engine: OpenAISignalEngine,
        risk_manager: RiskManager,
        settings: RiskSettings,
        logger: JsonlLogger,
    ) -> None:
        self.mt5 = mt5
        self.signal_engine = signal_engine
        self.risk_manager = risk_manager
        self.settings = settings
        self.logger = logger
        self.state = TradingEngineState()

    def set_settings(self, settings: RiskSettings) -> None:
        self.settings = settings

    def set_emergency_stop(self, enabled: bool) -> None:
        self.state.emergency_stop = enabled
        self.logger.append("emergency_stop", {"enabled": enabled})

    def _symbol_risk_meta(self, symbol: str) -> dict[str, float]:
        info = self.mt5.get_symbol_info(symbol)
        if info is None:
            return {
                "point": 0.0,
                "pip_value_per_lot": 0.0,
                "volume_min": 0.01,
                "volume_max": 100.0,
                "volume_step": 0.01,
            }

        point = float(getattr(info, "point", 0.0))
        tick_value = float(getattr(info, "trade_tick_value", 0.0))
        tick_size = float(getattr(info, "trade_tick_size", 0.0))
        pip_value_per_lot = tick_value * (point / tick_size) if tick_size > 0 and point > 0 else 0.0

        return {
            "point": point,
            "pip_value_per_lot": pip_value_per_lot,
            "volume_min": float(getattr(info, "volume_min", 0.01)),
            "volume_max": float(getattr(info, "volume_max", 100.0)),
            "volume_step": float(getattr(info, "volume_step", 0.01)),
        }

    def analyze_once(self) -> CycleResult:
        symbol = self.settings.symbol
        timeframe = self.settings.timeframe

        account = self.mt5.get_account_snapshot()
        positions = self.mt5.get_positions(symbol=symbol)
        rates = self.mt5.get_rates(symbol=symbol, timeframe=timeframe, count=350)
        tick = self.mt5.get_latest_tick(symbol)
        if tick is None:
            raise RuntimeError("No tick data available")

        spread_points = self.mt5.get_spread_points(symbol)
        features = compute_features(
            rates=rates,
            symbol=symbol,
            timeframe=timeframe,
            bid=float(tick.bid),
            ask=float(tick.ask),
            spread_points=spread_points,
            open_positions=positions,
            account=account,
        )

        compact_payload = compact_feature_payload(features)
        compact_payload["risk_settings"] = {
            "mode": self.settings.mode.value,
            "min_confidence": self.settings.min_confidence,
            "max_risk_per_trade_pct": self.settings.max_risk_per_trade_pct,
            "max_daily_loss_pct": self.settings.max_daily_loss_pct,
            "max_trades_per_day": self.settings.max_trades_per_day,
            "max_open_positions": self.settings.max_open_positions,
        }

        signal = self.signal_engine.generate_signal(compact_payload)

        meta = self._symbol_risk_meta(symbol)
        trades_today = self.logger.count_event_today("order_sent")
        decision = self.risk_manager.evaluate(
            signal=signal,
            features=features,
            settings=self.settings,
            balance=account.balance,
            trades_today=trades_today,
            open_positions=len(positions),
            point=meta["point"],
            pip_value_per_lot=meta["pip_value_per_lot"],
            volume_min=meta["volume_min"],
            volume_max=meta["volume_max"],
            volume_step=meta["volume_step"],
        )

        result = CycleResult(
            mode=self.settings.mode,
            signal=signal,
            risk_decision=decision,
            blocked=not decision.allowed,
        )

        if not decision.allowed:
            self.logger.append(
                "blocked_trade",
                {
                    "mode": self.settings.mode.value,
                    "signal": signal.model_dump(),
                    "reasons": decision.reasons,
                },
            )

        if self.settings.mode == TradingMode.SIGNAL_ONLY:
            self.logger.append("signal_only", {"signal": signal.model_dump()})

        if self.settings.mode == TradingMode.SEMI_AUTO:
            can_propose = signal.action in (SignalAction.BUY, SignalAction.SELL) and decision.allowed
            if can_propose:
                proposal = TradeProposal(
                    signal=signal,
                    risk_decision=decision,
                    requested_symbol=symbol,
                    requested_timeframe=timeframe,
                )
                self.state.pending_proposal = proposal
                result.proposal = proposal
                self.logger.append("proposal_created", proposal.model_dump(mode="json"))

        if self.settings.mode == TradingMode.FULL_AUTO:
            if self.state.emergency_stop:
                self.logger.append("blocked_trade", {"reasons": ["Emergency stop is active"]})
                result.blocked = True
            elif not self.settings.trading_enabled:
                self.logger.append("blocked_trade", {"reasons": ["Trading is disabled"]})
                result.blocked = True
            elif decision.allowed and signal.action in (SignalAction.BUY, SignalAction.SELL):
                order_result = self._send_from_signal(signal, decision)
                result.order_result = order_result

        self.state.last_result = result
        return result

    def approve_pending_trade(self) -> dict[str, Any]:
        proposal = self.state.pending_proposal
        if proposal is None:
            return {"ok": False, "error": "No pending proposal"}
        if self.state.emergency_stop:
            return {"ok": False, "error": "Emergency stop is active"}
        if not self.settings.trading_enabled:
            return {"ok": False, "error": "Trading is disabled"}

        proposal.approved = True
        self.logger.append("proposal_approved", proposal.model_dump(mode="json"))

        result = self._send_from_signal(proposal.signal, proposal.risk_decision)
        if result.get("ok"):
            self.state.pending_proposal = None
        return result

    def _send_from_signal(self, signal, decision) -> dict[str, Any]:
        if decision.lot_size is None:
            out = {"ok": False, "error": "No lot size computed"}
            self.logger.append("blocked_trade", {"reasons": [out["error"]]})
            return out

        order_request = OrderRequest(
            symbol=self.settings.symbol,
            action=signal.action.value,
            volume=decision.lot_size,
            sl_pips=float(decision.normalized_stop_loss_pips or 0),
            tp_pips=float(decision.normalized_take_profit_pips or 0),
        )
        self.logger.append("order_request", self.mt5.order_request_to_dict(order_request))

        result = self.mt5.send_market_order(order_request)
        if result.get("ok"):
            self.logger.append("order_sent", result)
        else:
            self.logger.append("order_failed", result)
        return result

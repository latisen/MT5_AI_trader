from __future__ import annotations

import math

from models import AISignal, MarketFeatures, RiskDecision, RiskSettings, SignalAction, StopLossMethod


class RiskManager:
    def evaluate(
        self,
        signal: AISignal,
        features: MarketFeatures,
        settings: RiskSettings,
        balance: float,
        trades_today: int,
        open_positions: int,
        point: float,
        pip_value_per_lot: float,
        volume_min: float,
        volume_max: float,
        volume_step: float,
    ) -> RiskDecision:
        reasons: list[str] = []

        if signal.action == SignalAction.WAIT:
            reasons.append("Signal action is WAIT")

        if signal.confidence < settings.min_confidence:
            reasons.append(
                f"Confidence below threshold ({signal.confidence:.2f} < {settings.min_confidence:.2f})"
            )

        daily_loss_abs = abs(min(features.daily_pl, 0.0))
        daily_loss_limit = max(0.0, balance * settings.max_daily_loss_pct / 100.0)
        if daily_loss_abs >= daily_loss_limit > 0:
            reasons.append(
                f"Daily loss limit reached ({daily_loss_abs:.2f} >= {daily_loss_limit:.2f})"
            )

        if trades_today >= settings.max_trades_per_day:
            reasons.append(
                f"Max trades/day reached ({trades_today} >= {settings.max_trades_per_day})"
            )

        if open_positions >= settings.max_open_positions:
            reasons.append(
                f"Max open positions reached ({open_positions} >= {settings.max_open_positions})"
            )

        if features.spread_points > settings.max_spread_points:
            reasons.append(
                f"Spread too high ({features.spread_points:.2f} > {settings.max_spread_points:.2f})"
            )

        if signal.action in (SignalAction.BUY, SignalAction.SELL) and signal.stop_loss_pips is None:
            reasons.append("Stop loss missing in AI signal")

        normalized_sl_pips = signal.stop_loss_pips
        if settings.stop_loss_method == StopLossMethod.FIXED_PIPS:
            normalized_sl_pips = settings.fixed_stop_loss_pips
        elif settings.stop_loss_method == StopLossMethod.ATR_BASED and point > 0:
            atr_points = (features.atr14 / point) * settings.atr_multiplier
            normalized_sl_pips = max(float(signal.stop_loss_pips or 0.0), float(atr_points))

        if normalized_sl_pips <= 0:
            reasons.append("Stop loss pips invalid")

        normalized_tp_pips = signal.take_profit_pips
        if normalized_tp_pips is None and normalized_sl_pips > 0:
            normalized_tp_pips = normalized_sl_pips * settings.take_profit_rr

        lot_size = None
        if normalized_sl_pips > 0 and signal.action in (SignalAction.BUY, SignalAction.SELL):
            lot_size = self._compute_lot_size(
                balance=balance,
                max_risk_pct=settings.max_risk_per_trade_pct,
                sl_pips=normalized_sl_pips,
                pip_value_per_lot=pip_value_per_lot,
                volume_min=volume_min,
                volume_max=volume_max,
                volume_step=volume_step,
            )
            if lot_size is None:
                reasons.append("Position size invalid based on risk constraints")

        allowed = len(reasons) == 0
        return RiskDecision(
            allowed=allowed,
            reasons=reasons,
            lot_size=lot_size,
            normalized_stop_loss_pips=normalized_sl_pips,
            normalized_take_profit_pips=normalized_tp_pips,
        )

    def _compute_lot_size(
        self,
        balance: float,
        max_risk_pct: float,
        sl_pips: float,
        pip_value_per_lot: float,
        volume_min: float,
        volume_max: float,
        volume_step: float,
    ) -> float | None:
        if balance <= 0 or max_risk_pct <= 0 or sl_pips <= 0 or pip_value_per_lot <= 0:
            return None

        risk_amount = balance * max_risk_pct / 100.0
        raw_lots = risk_amount / (sl_pips * pip_value_per_lot)
        if not math.isfinite(raw_lots) or raw_lots <= 0:
            return None

        if volume_step <= 0:
            volume_step = 0.01

        # Snap to broker lot step.
        stepped = math.floor(raw_lots / volume_step) * volume_step
        stepped = max(volume_min, min(stepped, volume_max))
        stepped = round(stepped, 2)

        if stepped < volume_min or stepped > volume_max:
            return None
        return stepped

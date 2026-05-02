from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class TradingMode(str, Enum):
    SIGNAL_ONLY = "SIGNAL_ONLY"
    SEMI_AUTO = "SEMI_AUTO"
    FULL_AUTO = "FULL_AUTO"


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"


class EntryType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    NONE = "NONE"


class MarketRegime(str, Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    UNCLEAR = "UNCLEAR"


class StopLossMethod(str, Enum):
    FIXED_PIPS = "FIXED_PIPS"
    ATR_BASED = "ATR_BASED"


class AISignal(BaseModel):
    action: SignalAction
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=2000)
    entry_type: EntryType
    stop_loss_pips: float | None = Field(default=None, gt=0)
    take_profit_pips: float | None = Field(default=None, gt=0)
    risk_notes: list[str] = Field(default_factory=list)
    market_regime: MarketRegime


class RiskSettings(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "M15"
    max_risk_per_trade_pct: float = Field(default=1.0, gt=0.0, le=5.0)
    max_daily_loss_pct: float = Field(default=3.0, gt=0.0, le=20.0)
    max_trades_per_day: int = Field(default=5, ge=1, le=100)
    max_open_positions: int = Field(default=2, ge=0, le=50)
    min_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    stop_loss_method: StopLossMethod = StopLossMethod.ATR_BASED
    fixed_stop_loss_pips: float = Field(default=20.0, gt=0.1, le=2000)
    atr_multiplier: float = Field(default=1.5, gt=0.1, le=20.0)
    take_profit_rr: float = Field(default=2.0, gt=0.1, le=20.0)
    max_spread_points: float = Field(default=30.0, gt=0.0, le=10000.0)
    analyze_on_new_candle_only: bool = True
    trading_enabled: bool = False
    mode: TradingMode = TradingMode.SIGNAL_ONLY

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("timeframe")
    @classmethod
    def normalize_timeframe(cls, value: str) -> str:
        return value.strip().upper()


class AccountSnapshot(BaseModel):
    login: int | None = None
    server: str | None = None
    balance: float = 0.0
    equity: float = 0.0
    margin_free: float = 0.0
    daily_pl: float = 0.0


class PositionSnapshot(BaseModel):
    ticket: int
    symbol: str
    type: str
    volume: float
    price_open: float
    sl: float
    tp: float
    profit: float
    time: datetime


class MarketFeatures(BaseModel):
    symbol: str
    timeframe: str
    bid: float
    ask: float
    spread_points: float
    ema20: float
    ema50: float
    ema200: float
    rsi14: float
    atr14: float
    trend: str
    volatility_pct: float
    recent_candles: list[dict[str, float]]
    open_positions_count: int
    daily_pl: float


class RiskDecision(BaseModel):
    allowed: bool
    reasons: list[str] = Field(default_factory=list)
    lot_size: float | None = None
    normalized_stop_loss_pips: float | None = None
    normalized_take_profit_pips: float | None = None


class TradeProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    signal: AISignal
    risk_decision: RiskDecision
    requested_symbol: str
    requested_timeframe: str
    approved: bool = False


class CycleResult(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    mode: TradingMode
    signal: AISignal
    risk_decision: RiskDecision
    proposal: TradeProposal | None = None
    order_result: dict[str, Any] | None = None
    blocked: bool = False


class LogRecord(BaseModel):
    ts: datetime = Field(default_factory=datetime.utcnow)
    event: str
    payload: dict[str, Any]

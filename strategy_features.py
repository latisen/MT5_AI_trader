from __future__ import annotations

import numpy as np
import pandas as pd

from models import AccountSnapshot, MarketFeatures, PositionSnapshot


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.rolling(window=period, min_periods=period).mean().bfill()


def _trend_label(ema20: float, ema50: float, ema200: float, close: float) -> str:
    if close > ema20 > ema50 > ema200:
        return "UPTREND"
    if close < ema20 < ema50 < ema200:
        return "DOWNTREND"
    return "SIDEWAYS"


def compute_features(
    rates: pd.DataFrame,
    symbol: str,
    timeframe: str,
    bid: float,
    ask: float,
    spread_points: float,
    open_positions: list[PositionSnapshot],
    account: AccountSnapshot,
) -> MarketFeatures:
    df = rates.copy()
    close = df["close"]

    ema20_series = _ema(close, 20)
    ema50_series = _ema(close, 50)
    ema200_series = _ema(close, 200)
    rsi14_series = _rsi(close, 14)
    atr14_series = _atr(df, 14)

    ret = close.pct_change().dropna()
    volatility_pct = float(ret.tail(30).std() * 100) if len(ret) > 30 else float(ret.std() * 100)

    last_close = float(close.iloc[-1])
    ema20 = float(ema20_series.iloc[-1])
    ema50 = float(ema50_series.iloc[-1])
    ema200 = float(ema200_series.iloc[-1])
    rsi14 = float(rsi14_series.iloc[-1])
    atr14 = float(atr14_series.iloc[-1])

    recent_candles = (
        df[["open", "high", "low", "close", "tick_volume"]]
        .tail(5)
        .round(6)
        .to_dict(orient="records")
    )

    trend = _trend_label(ema20=ema20, ema50=ema50, ema200=ema200, close=last_close)

    return MarketFeatures(
        symbol=symbol,
        timeframe=timeframe,
        bid=float(bid),
        ask=float(ask),
        spread_points=float(spread_points),
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        rsi14=rsi14,
        atr14=atr14,
        trend=trend,
        volatility_pct=float(volatility_pct),
        recent_candles=recent_candles,
        open_positions_count=len(open_positions),
        daily_pl=account.daily_pl,
    )


def compact_feature_payload(features: MarketFeatures) -> dict:
    return {
        "symbol": features.symbol,
        "timeframe": features.timeframe,
        "trend": features.trend,
        "ema": {
            "ema20": round(features.ema20, 6),
            "ema50": round(features.ema50, 6),
            "ema200": round(features.ema200, 6),
        },
        "rsi14": round(features.rsi14, 3),
        "atr14": round(features.atr14, 6),
        "spread_points": round(features.spread_points, 3),
        "volatility_pct": round(features.volatility_pct, 4),
        "recent_candles": features.recent_candles,
        "open_positions_count": features.open_positions_count,
        "daily_pl": round(features.daily_pl, 2),
    }

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from models import AccountSnapshot, PositionSnapshot

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None


_TIMEFRAME_MAP = {
    "M1": getattr(mt5, "TIMEFRAME_M1", None),
    "M5": getattr(mt5, "TIMEFRAME_M5", None),
    "M15": getattr(mt5, "TIMEFRAME_M15", None),
    "M30": getattr(mt5, "TIMEFRAME_M30", None),
    "H1": getattr(mt5, "TIMEFRAME_H1", None),
    "H4": getattr(mt5, "TIMEFRAME_H4", None),
    "D1": getattr(mt5, "TIMEFRAME_D1", None),
}


@dataclass
class OrderRequest:
    symbol: str
    action: str
    volume: float
    sl_pips: float
    tp_pips: float
    comment: str = "MT5_AI_TRADER"


class MT5Client:
    def __init__(self, login: int, password: str, server: str, terminal_path: str | None = None) -> None:
        self.login = login
        self.password = password
        self.server = server
        self.terminal_path = terminal_path
        self.connected = False

    def initialize(self) -> bool:
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed.")

        kwargs: dict[str, Any] = {}
        if self.terminal_path:
            kwargs["path"] = self.terminal_path

        if not mt5.initialize(**kwargs):
            return False

        authorized = mt5.login(self.login, password=self.password, server=self.server)
        self.connected = bool(authorized)
        return self.connected

    def shutdown(self) -> None:
        if mt5 is not None:
            mt5.shutdown()
        self.connected = False

    def ensure_symbol(self, symbol: str) -> bool:
        info = mt5.symbol_info(symbol)
        if info is None:
            return False
        if not info.visible:
            return bool(mt5.symbol_select(symbol, True))
        return True

    def timeframe_code(self, timeframe: str) -> int:
        code = _TIMEFRAME_MAP.get(timeframe.upper())
        if code is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        return code

    def get_account_snapshot(self) -> AccountSnapshot:
        info = mt5.account_info()
        if info is None:
            return AccountSnapshot()

        daily_pl = self.get_today_closed_pl()
        return AccountSnapshot(
            login=getattr(info, "login", None),
            server=getattr(info, "server", None),
            balance=float(getattr(info, "balance", 0.0)),
            equity=float(getattr(info, "equity", 0.0)),
            margin_free=float(getattr(info, "margin_free", 0.0)),
            daily_pl=float(daily_pl),
        )

    def get_today_closed_pl(self) -> float:
        now = datetime.utcnow()
        day_start = datetime(now.year, now.month, now.day)
        deals = mt5.history_deals_get(day_start, now)
        if deals is None:
            return 0.0

        total = 0.0
        for deal in deals:
            total += float(getattr(deal, "profit", 0.0))
            total += float(getattr(deal, "commission", 0.0))
            total += float(getattr(deal, "swap", 0.0))
        return total

    def get_positions(self, symbol: str | None = None) -> list[PositionSnapshot]:
        raw = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if raw is None:
            return []

        mapped: list[PositionSnapshot] = []
        for p in raw:
            pos_type = "BUY" if int(getattr(p, "type", 0)) == mt5.POSITION_TYPE_BUY else "SELL"
            mapped.append(
                PositionSnapshot(
                    ticket=int(getattr(p, "ticket", 0)),
                    symbol=str(getattr(p, "symbol", "")),
                    type=pos_type,
                    volume=float(getattr(p, "volume", 0.0)),
                    price_open=float(getattr(p, "price_open", 0.0)),
                    sl=float(getattr(p, "sl", 0.0)),
                    tp=float(getattr(p, "tp", 0.0)),
                    profit=float(getattr(p, "profit", 0.0)),
                    time=datetime.utcfromtimestamp(int(getattr(p, "time", 0))),
                )
            )
        return mapped

    def get_latest_tick(self, symbol: str) -> Any:
        return mt5.symbol_info_tick(symbol)

    def get_symbol_info(self, symbol: str) -> Any:
        return mt5.symbol_info(symbol)

    def get_spread_points(self, symbol: str) -> float:
        tick = self.get_latest_tick(symbol)
        info = self.get_symbol_info(symbol)
        if tick is None or info is None:
            return 0.0
        point = float(getattr(info, "point", 0.0))
        if point <= 0:
            return 0.0
        return max(0.0, (float(tick.ask) - float(tick.bid)) / point)

    def get_rates(self, symbol: str, timeframe: str, count: int = 300) -> pd.DataFrame:
        if not self.ensure_symbol(symbol):
            raise RuntimeError(f"Could not select symbol: {symbol}")

        tf_code = self.timeframe_code(timeframe)
        rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, count)
        if rates is None or len(rates) == 0:
            raise RuntimeError("No rates returned from MT5")

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    def send_market_order(self, request: OrderRequest) -> dict[str, Any]:
        if not self.ensure_symbol(request.symbol):
            return {"ok": False, "error": f"Symbol not available: {request.symbol}"}

        tick = self.get_latest_tick(request.symbol)
        info = self.get_symbol_info(request.symbol)
        if tick is None or info is None:
            return {"ok": False, "error": "Missing tick/symbol info"}

        point = float(getattr(info, "point", 0.0))
        digits = int(getattr(info, "digits", 5))
        if point <= 0:
            return {"ok": False, "error": "Invalid point size"}

        action = request.action.upper()
        if action == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = float(tick.ask)
            sl_price = round(price - request.sl_pips * point, digits)
            tp_price = round(price + request.tp_pips * point, digits)
        elif action == "SELL":
            order_type = mt5.ORDER_TYPE_SELL
            price = float(tick.bid)
            sl_price = round(price + request.sl_pips * point, digits)
            tp_price = round(price - request.tp_pips * point, digits)
        else:
            return {"ok": False, "error": f"Unsupported action: {request.action}"}

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": request.symbol,
            "volume": float(request.volume),
            "type": order_type,
            "price": price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 20,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
            "comment": request.comment,
        }

        result = mt5.order_send(req)
        if result is None:
            return {"ok": False, "error": "order_send returned None", "request": req}

        return {
            "ok": int(getattr(result, "retcode", 0)) == mt5.TRADE_RETCODE_DONE,
            "retcode": int(getattr(result, "retcode", -1)),
            "comment": str(getattr(result, "comment", "")),
            "order": int(getattr(result, "order", 0)),
            "deal": int(getattr(result, "deal", 0)),
            "request": req,
        }

    @staticmethod
    def order_request_to_dict(req: OrderRequest) -> dict[str, Any]:
        return asdict(req)

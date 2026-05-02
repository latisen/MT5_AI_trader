from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from models import RiskSettings

_DAY_MAP = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}


@dataclass
class MarketClock:
    is_open: bool
    now_utc: datetime
    next_event_type: str
    next_event_at_utc: datetime

    @property
    def seconds_to_next_event(self) -> int:
        return max(0, int((self.next_event_at_utc - self.now_utc).total_seconds()))


def parse_weekday(name: str) -> int:
    key = name.strip().upper()
    if key not in _DAY_MAP:
        raise ValueError(f"Invalid weekday: {name}")
    return _DAY_MAP[key]


def parse_hhmm(value: str) -> tuple[int, int]:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid HH:MM value: {value}")
    hh = int(parts[0])
    mm = int(parts[1])
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        raise ValueError(f"Invalid HH:MM value: {value}")
    return hh, mm


def _next_occurrence(now: datetime, weekday: int, hh: int, mm: int) -> datetime:
    base = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    days_ahead = (weekday - now.weekday()) % 7
    candidate = base + timedelta(days=days_ahead)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def _prev_occurrence(now: datetime, weekday: int, hh: int, mm: int) -> datetime:
    base = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    days_back = (now.weekday() - weekday) % 7
    candidate = base - timedelta(days=days_back)
    if candidate > now:
        candidate -= timedelta(days=7)
    return candidate


def get_market_clock(settings: RiskSettings, now_utc: datetime | None = None) -> MarketClock:
    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    if not settings.market_hours_enabled:
        # Always open in this mode, but still expose a synthetic next check event.
        return MarketClock(
            is_open=True,
            now_utc=now,
            next_event_type="CHECK",
            next_event_at_utc=now + timedelta(minutes=1),
        )

    open_weekday = parse_weekday(settings.market_open_day)
    close_weekday = parse_weekday(settings.market_close_day)
    open_hh, open_mm = parse_hhmm(settings.market_open_time_utc)
    close_hh, close_mm = parse_hhmm(settings.market_close_time_utc)

    prev_open = _prev_occurrence(now, open_weekday, open_hh, open_mm)
    prev_close = _prev_occurrence(now, close_weekday, close_hh, close_mm)
    is_open = prev_open > prev_close

    if is_open:
        next_close = _next_occurrence(now, close_weekday, close_hh, close_mm)
        return MarketClock(
            is_open=True,
            now_utc=now,
            next_event_type="CLOSE",
            next_event_at_utc=next_close,
        )

    next_open = _next_occurrence(now, open_weekday, open_hh, open_mm)
    return MarketClock(
        is_open=False,
        now_utc=now,
        next_event_type="OPEN",
        next_event_at_utc=next_open,
    )


def format_countdown(total_seconds: int) -> str:
    seconds = max(0, int(total_seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours:02d}h {minutes:02d}m {sec:02d}s"
    return f"{hours:02d}h {minutes:02d}m {sec:02d}s"

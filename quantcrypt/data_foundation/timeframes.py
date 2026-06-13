from __future__ import annotations

from datetime import UTC, datetime


INTERVAL_TO_MS: dict[str, int] = {
    "1s": 1_000,
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}


def interval_to_data_vision(interval: str) -> str:
    return "1mo" if interval == "1M" else interval


def next_open_time_ms(open_time_ms: int, interval: str) -> int:
    if interval == "1M":
        current = datetime.fromtimestamp(open_time_ms / 1000, tz=UTC)
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        return int(datetime(year, month, 1, tzinfo=UTC).timestamp() * 1000)
    return open_time_ms + INTERVAL_TO_MS[interval]


def iter_open_times(start_open_time_ms: int, end_open_time_ms: int, interval: str) -> list[int]:
    values: list[int] = []
    cursor = start_open_time_ms
    while cursor < end_open_time_ms:
        values.append(cursor)
        cursor = next_open_time_ms(cursor, interval)
    return values


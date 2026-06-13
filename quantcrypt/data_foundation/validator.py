from __future__ import annotations

from .models import OHLCVCandle, ValidationGap, ValidationReport
from .timeframes import iter_open_times, next_open_time_ms


def validate_candle_sequence(
    candles: list[OHLCVCandle],
    *,
    interval: str,
    start_open_time_ms: int,
    end_open_time_ms: int,
) -> ValidationReport:
    seen: set[int] = set()
    duplicates: list[int] = []
    invalid: list[int] = []

    for candle in candles:
        if candle.open_time_ms in seen:
            duplicates.append(candle.open_time_ms)
            continue
        seen.add(candle.open_time_ms)
        if (
            candle.close_time_ms <= candle.open_time_ms
            or candle.high_price < candle.low_price
            or candle.high_price < max(candle.open_price, candle.close_price)
            or candle.low_price > min(candle.open_price, candle.close_price)
        ):
            invalid.append(candle.open_time_ms)

    expected_open_times = iter_open_times(start_open_time_ms, end_open_time_ms, interval)
    missing = [open_time for open_time in expected_open_times if open_time not in seen]
    return ValidationReport(
        expected_count=len(expected_open_times),
        actual_count=len(candles),
        missing_open_times_ms=missing,
        duplicate_open_times_ms=duplicates,
        invalid_open_times_ms=invalid,
    )


def group_missing_candles(missing_open_times_ms: list[int], interval: str) -> list[ValidationGap]:
    if not missing_open_times_ms:
        return []

    gaps: list[ValidationGap] = []
    start = missing_open_times_ms[0]
    previous = missing_open_times_ms[0]
    count = 1

    for open_time_ms in missing_open_times_ms[1:]:
        expected_next = next_open_time_ms(previous, interval)
        if open_time_ms == expected_next:
            previous = open_time_ms
            count += 1
            continue
        gaps.append(
            ValidationGap(
                start_open_time_ms=start,
                end_open_time_ms=next_open_time_ms(previous, interval),
                missing_count=count,
            )
        )
        start = open_time_ms
        previous = open_time_ms
        count = 1

    gaps.append(
        ValidationGap(
            start_open_time_ms=start,
            end_open_time_ms=next_open_time_ms(previous, interval),
            missing_count=count,
        )
    )
    return gaps


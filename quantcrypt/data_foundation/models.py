from __future__ import annotations

from dataclasses import dataclass


def normalize_binance_timestamp(raw_timestamp: int) -> int:
    if raw_timestamp >= 10_000_000_000_000:
        return raw_timestamp // 1000
    return raw_timestamp


@dataclass(slots=True)
class OHLCVCandle:
    exchange: str
    market_type: str
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    quote_asset_volume: float
    trade_count: int
    taker_buy_base_volume: float
    taker_buy_quote_volume: float
    is_closed: bool
    source: str

    def __post_init__(self) -> None:
        self.open_time_ms = normalize_binance_timestamp(int(self.open_time_ms))
        self.close_time_ms = normalize_binance_timestamp(int(self.close_time_ms))
        if self.close_time_ms <= self.open_time_ms:
            raise ValueError("close_time_ms must be greater than open_time_ms")
        if self.high_price < self.low_price:
            raise ValueError("high_price must be greater than or equal to low_price")
        if self.high_price < max(self.open_price, self.close_price):
            raise ValueError("high_price is below open or close price")
        if self.low_price > min(self.open_price, self.close_price):
            raise ValueError("low_price is above open or close price")

    @classmethod
    def from_rest_row(
        cls,
        row: list[object],
        *,
        symbol: str,
        interval: str,
        market_type: str,
        source: str,
    ) -> "OHLCVCandle":
        return cls(
            exchange="binance",
            market_type=market_type,
            symbol=symbol,
            interval=interval,
            open_time_ms=int(row[0]),
            open_price=float(row[1]),
            high_price=float(row[2]),
            low_price=float(row[3]),
            close_price=float(row[4]),
            volume=float(row[5]),
            close_time_ms=int(row[6]),
            quote_asset_volume=float(row[7]),
            trade_count=int(row[8]),
            taker_buy_base_volume=float(row[9]),
            taker_buy_quote_volume=float(row[10]),
            is_closed=True,
            source=source,
        )

    @classmethod
    def from_ws_payload(
        cls,
        payload: dict[str, object],
        *,
        market_type: str,
        source: str,
    ) -> "OHLCVCandle":
        return cls(
            exchange="binance",
            market_type=market_type,
            symbol=str(payload["s"]),
            interval=str(payload["i"]),
            open_time_ms=int(payload["t"]),
            close_time_ms=int(payload["T"]),
            open_price=float(payload["o"]),
            high_price=float(payload["h"]),
            low_price=float(payload["l"]),
            close_price=float(payload["c"]),
            volume=float(payload["v"]),
            quote_asset_volume=float(payload["q"]),
            trade_count=int(payload["n"]),
            taker_buy_base_volume=float(payload["V"]),
            taker_buy_quote_volume=float(payload["Q"]),
            is_closed=bool(payload["x"]),
            source=source,
        )


@dataclass(slots=True)
class ValidationGap:
    start_open_time_ms: int
    end_open_time_ms: int
    missing_count: int


@dataclass(slots=True)
class ValidationReport:
    expected_count: int
    actual_count: int
    missing_open_times_ms: list[int]
    duplicate_open_times_ms: list[int]
    invalid_open_times_ms: list[int]
    repaired_count: int = 0

    @property
    def is_clean(self) -> bool:
        return (
            not self.missing_open_times_ms
            and not self.duplicate_open_times_ms
            and not self.invalid_open_times_ms
        )


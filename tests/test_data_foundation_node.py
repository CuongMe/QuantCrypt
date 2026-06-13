from pathlib import Path

from quantcrypt.data_foundation.models import OHLCVCandle
from quantcrypt.data_foundation.node import DataFoundationNode
from quantcrypt.data_foundation.storage import SQLiteOHLCVStore


def _candle(open_time_ms: int) -> OHLCVCandle:
    return OHLCVCandle(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        interval="1m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + 59_999,
        open_price=100.0,
        high_price=110.0,
        low_price=90.0,
        close_price=105.0,
        volume=10.0,
        quote_asset_volume=1000.0,
        trade_count=10,
        taker_buy_base_volume=4.0,
        taker_buy_quote_volume=400.0,
        is_closed=True,
        source="rest",
    )


class StubRestCollector:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def backfill_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
    ) -> list[OHLCVCandle]:
        self.calls.append((start_time_ms, end_time_ms))
        return [_candle(60_000)]


def test_validate_and_repair_fills_missing_candle(tmp_path: Path) -> None:
    db_path = tmp_path / "foundation.sqlite3"
    store = SQLiteOHLCVStore(db_path)
    store.upsert_candles([_candle(0), _candle(120_000)])
    rest = StubRestCollector()

    node = DataFoundationNode(
        db_path=db_path,
        store=store,
        rest_collector=rest,
    )
    report = node.validate_and_repair(
        symbol="BTCUSDT",
        interval="1m",
        start_open_time_ms=0,
        end_open_time_ms=180_000,
    )

    assert rest.calls == [(60_000, 120_000)]
    assert report.repaired_count == 1
    assert report.is_clean is True
    assert [candle.open_time_ms for candle in node.load_clean_ohlcv(symbol="BTCUSDT", interval="1m")] == [
        0,
        60_000,
        120_000,
    ]


from __future__ import annotations

from datetime import date
from pathlib import Path

from ..paths import DEFAULT_DB_PATH
from .collectors import BinanceBulkDownloader, BinanceRestCollector, BinanceWebSocketCollector
from .models import OHLCVCandle, ValidationReport
from .storage import SQLiteOHLCVStore
from .validator import group_missing_candles, validate_candle_sequence


class DataFoundationNode:
    def __init__(
        self,
        *,
        db_path: str | Path = DEFAULT_DB_PATH,
        store: SQLiteOHLCVStore | None = None,
        rest_collector: BinanceRestCollector | None = None,
        ws_collector: BinanceWebSocketCollector | None = None,
        bulk_downloader: BinanceBulkDownloader | None = None,
    ) -> None:
        self.store = store or SQLiteOHLCVStore(db_path)
        self.rest_collector = rest_collector or BinanceRestCollector()
        self.ws_collector = ws_collector or BinanceWebSocketCollector()
        self.bulk_downloader = bulk_downloader or BinanceBulkDownloader()

    def backfill_rest_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
    ) -> int:
        candles = self.rest_collector.backfill_klines(
            symbol=symbol,
            interval=interval,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
        return self.store.upsert_candles(candles)

    def download_bulk_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start_date: date,
        end_date: date,
    ) -> int:
        candles = self.bulk_downloader.download_date_range(
            symbol=symbol,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )
        return self.store.upsert_candles(candles)

    async def collect_live_klines(
        self,
        *,
        symbol: str,
        interval: str,
        stop_after: int | None = None,
    ) -> int:
        async def on_closed_candle(candle: OHLCVCandle) -> None:
            self.store.upsert_candles([candle])

        return await self.ws_collector.collect_live_klines(
            symbol=symbol,
            interval=interval,
            on_closed_candle=on_closed_candle,
            stop_after=stop_after,
        )

    def load_clean_ohlcv(
        self,
        *,
        symbol: str,
        interval: str,
        start_open_time_ms: int | None = None,
        end_open_time_ms: int | None = None,
    ) -> list[OHLCVCandle]:
        return self.store.fetch_candles(
            symbol=symbol,
            interval=interval,
            start_open_time_ms=start_open_time_ms,
            end_open_time_ms=end_open_time_ms,
        )

    def load_latest_clean_ohlcv(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[OHLCVCandle]:
        return self.store.fetch_latest_candles(
            symbol=symbol,
            interval=interval,
            limit=limit,
        )

    def validate_and_repair(
        self,
        *,
        symbol: str,
        interval: str,
        start_open_time_ms: int,
        end_open_time_ms: int,
    ) -> ValidationReport:
        initial_report = validate_candle_sequence(
            self.load_clean_ohlcv(
                symbol=symbol,
                interval=interval,
                start_open_time_ms=start_open_time_ms,
                end_open_time_ms=end_open_time_ms,
            ),
            interval=interval,
            start_open_time_ms=start_open_time_ms,
            end_open_time_ms=end_open_time_ms,
        )
        repaired_count = 0
        for gap in group_missing_candles(initial_report.missing_open_times_ms, interval):
            repaired_count += self.backfill_rest_klines(
                symbol=symbol,
                interval=interval,
                start_time_ms=gap.start_open_time_ms,
                end_time_ms=gap.end_open_time_ms,
            )

        final_report = validate_candle_sequence(
            self.load_clean_ohlcv(
                symbol=symbol,
                interval=interval,
                start_open_time_ms=start_open_time_ms,
                end_open_time_ms=end_open_time_ms,
            ),
            interval=interval,
            start_open_time_ms=start_open_time_ms,
            end_open_time_ms=end_open_time_ms,
        )
        final_report.repaired_count = repaired_count
        return final_report

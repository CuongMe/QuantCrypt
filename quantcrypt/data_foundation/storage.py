from __future__ import annotations

import time
from pathlib import Path

from ..sqlite_utils import connect_sqlite, initialize_sqlite_schema, prepare_sqlite_path
from .models import OHLCVCandle


class SQLiteOHLCVStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = prepare_sqlite_path(db_path)
        self.initialize_schema()

    def _connect(self):
        return connect_sqlite(self.db_path)

    def initialize_schema(self) -> None:
        initialize_sqlite_schema(
            self.db_path,
            """
            CREATE TABLE IF NOT EXISTS clean_ohlcv (
                exchange TEXT NOT NULL,
                market_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                open_time_ms INTEGER NOT NULL,
                close_time_ms INTEGER NOT NULL,
                open_price REAL NOT NULL,
                high_price REAL NOT NULL,
                low_price REAL NOT NULL,
                close_price REAL NOT NULL,
                volume REAL NOT NULL,
                quote_asset_volume REAL NOT NULL,
                trade_count INTEGER NOT NULL,
                taker_buy_base_volume REAL NOT NULL,
                taker_buy_quote_volume REAL NOT NULL,
                is_closed INTEGER NOT NULL CHECK (is_closed IN (0, 1)),
                source TEXT NOT NULL,
                ingested_at_ms INTEGER NOT NULL,
                PRIMARY KEY (exchange, market_type, symbol, interval, open_time_ms),
                CHECK (close_time_ms > open_time_ms),
                CHECK (high_price >= low_price)
            );

            CREATE INDEX IF NOT EXISTS idx_clean_ohlcv_lookup
            ON clean_ohlcv (exchange, market_type, symbol, interval, open_time_ms);
            """,
        )

    def upsert_candles(self, candles: list[OHLCVCandle]) -> int:
        if not candles:
            return 0
        ingested_at_ms = int(time.time() * 1000)
        rows = [
            (
                candle.exchange,
                candle.market_type,
                candle.symbol,
                candle.interval,
                candle.open_time_ms,
                candle.close_time_ms,
                candle.open_price,
                candle.high_price,
                candle.low_price,
                candle.close_price,
                candle.volume,
                candle.quote_asset_volume,
                candle.trade_count,
                candle.taker_buy_base_volume,
                candle.taker_buy_quote_volume,
                int(candle.is_closed),
                candle.source,
                ingested_at_ms,
            )
            for candle in candles
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO clean_ohlcv (
                    exchange, market_type, symbol, interval, open_time_ms, close_time_ms,
                    open_price, high_price, low_price, close_price, volume, quote_asset_volume,
                    trade_count, taker_buy_base_volume, taker_buy_quote_volume, is_closed,
                    source, ingested_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, market_type, symbol, interval, open_time_ms)
                DO UPDATE SET
                    close_time_ms=excluded.close_time_ms,
                    open_price=excluded.open_price,
                    high_price=excluded.high_price,
                    low_price=excluded.low_price,
                    close_price=excluded.close_price,
                    volume=excluded.volume,
                    quote_asset_volume=excluded.quote_asset_volume,
                    trade_count=excluded.trade_count,
                    taker_buy_base_volume=excluded.taker_buy_base_volume,
                    taker_buy_quote_volume=excluded.taker_buy_quote_volume,
                    is_closed=excluded.is_closed,
                    source=excluded.source,
                    ingested_at_ms=excluded.ingested_at_ms
                """,
                rows,
            )
        return len(candles)

    def fetch_candles(
        self,
        *,
        symbol: str,
        interval: str,
        start_open_time_ms: int | None = None,
        end_open_time_ms: int | None = None,
        exchange: str = "binance",
        market_type: str = "spot",
    ) -> list[OHLCVCandle]:
        clauses = [
            "exchange = ?",
            "market_type = ?",
            "symbol = ?",
            "interval = ?",
        ]
        params: list[object] = [exchange, market_type, symbol, interval]
        if start_open_time_ms is not None:
            clauses.append("open_time_ms >= ?")
            params.append(start_open_time_ms)
        if end_open_time_ms is not None:
            clauses.append("open_time_ms < ?")
            params.append(end_open_time_ms)

        query = f"""
            SELECT exchange, market_type, symbol, interval, open_time_ms, close_time_ms,
                   open_price, high_price, low_price, close_price, volume, quote_asset_volume,
                   trade_count, taker_buy_base_volume, taker_buy_quote_volume, is_closed, source
            FROM clean_ohlcv
            WHERE {' AND '.join(clauses)}
            ORDER BY open_time_ms ASC
        """
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            OHLCVCandle(
                exchange=row["exchange"],
                market_type=row["market_type"],
                symbol=row["symbol"],
                interval=row["interval"],
                open_time_ms=row["open_time_ms"],
                close_time_ms=row["close_time_ms"],
                open_price=row["open_price"],
                high_price=row["high_price"],
                low_price=row["low_price"],
                close_price=row["close_price"],
                volume=row["volume"],
                quote_asset_volume=row["quote_asset_volume"],
                trade_count=row["trade_count"],
                taker_buy_base_volume=row["taker_buy_base_volume"],
                taker_buy_quote_volume=row["taker_buy_quote_volume"],
                is_closed=bool(row["is_closed"]),
                source=row["source"],
            )
            for row in rows
        ]

    def fetch_latest_candles(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int,
        exchange: str = "binance",
        market_type: str = "spot",
    ) -> list[OHLCVCandle]:
        if limit <= 0:
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT exchange, market_type, symbol, interval, open_time_ms, close_time_ms,
                       open_price, high_price, low_price, close_price, volume, quote_asset_volume,
                       trade_count, taker_buy_base_volume, taker_buy_quote_volume, is_closed, source
                FROM clean_ohlcv
                WHERE exchange = ? AND market_type = ? AND symbol = ? AND interval = ?
                ORDER BY open_time_ms DESC
                LIMIT ?
                """,
                (exchange, market_type, symbol, interval, limit),
            ).fetchall()
        rows = list(reversed(rows))
        return [
            OHLCVCandle(
                exchange=row["exchange"],
                market_type=row["market_type"],
                symbol=row["symbol"],
                interval=row["interval"],
                open_time_ms=row["open_time_ms"],
                close_time_ms=row["close_time_ms"],
                open_price=row["open_price"],
                high_price=row["high_price"],
                low_price=row["low_price"],
                close_price=row["close_price"],
                volume=row["volume"],
                quote_asset_volume=row["quote_asset_volume"],
                trade_count=row["trade_count"],
                taker_buy_base_volume=row["taker_buy_base_volume"],
                taker_buy_quote_volume=row["taker_buy_quote_volume"],
                is_closed=bool(row["is_closed"]),
                source=row["source"],
            )
            for row in rows
        ]

    def count_candles(
        self,
        *,
        symbol: str,
        interval: str,
        exchange: str = "binance",
        market_type: str = "spot",
    ) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM clean_ohlcv
                    WHERE exchange = ? AND market_type = ? AND symbol = ? AND interval = ?
                    """,
                    (exchange, market_type, symbol, interval),
                ).fetchone()[0]
            )

    def fetch_latest_candle(
        self,
        *,
        symbol: str,
        interval: str,
        exchange: str = "binance",
        market_type: str = "spot",
    ) -> OHLCVCandle | None:
        candles = self.fetch_latest_candles(
            symbol=symbol,
            interval=interval,
            limit=1,
            exchange=exchange,
            market_type=market_type,
        )
        if not candles:
            return None
        return candles[0]

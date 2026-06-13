from __future__ import annotations

import json
import time
from typing import Callable
from urllib import error, parse, request

from ..models import OHLCVCandle
from ..timeframes import next_open_time_ms
from .binance_rate_limiter import BinanceRateLimiter


JsonGetter = Callable[[str, dict[str, object]], list[list[object]]]


class BinanceRestCollector:
    def __init__(
        self,
        *,
        base_url: str = "https://data-api.binance.vision",
        market_type: str = "spot",
        rate_limiter: BinanceRateLimiter | None = None,
        http_get_json: JsonGetter | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.market_type = market_type
        self.rate_limiter = rate_limiter or BinanceRateLimiter()
        self.http_get_json = http_get_json or self._http_get_json

    def fetch_klines_page(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        limit: int = 1000,
    ) -> list[OHLCVCandle]:
        params: dict[str, object] = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_time_ms is not None:
            params["startTime"] = start_time_ms
        if end_time_ms is not None:
            params["endTime"] = end_time_ms

        rows = self.http_get_json(f"{self.base_url}/api/v3/klines", params)
        return [
            OHLCVCandle.from_rest_row(
                row,
                symbol=symbol,
                interval=interval,
                market_type=self.market_type,
                source="rest",
            )
            for row in rows
        ]

    def backfill_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 1000,
    ) -> list[OHLCVCandle]:
        if start_time_ms >= end_time_ms:
            return []

        candles: list[OHLCVCandle] = []
        cursor = start_time_ms
        while cursor < end_time_ms:
            page = self.fetch_klines_page(
                symbol=symbol,
                interval=interval,
                start_time_ms=cursor,
                end_time_ms=end_time_ms - 1,
                limit=limit,
            )
            if not page:
                break
            candles.extend(page)
            next_cursor = next_open_time_ms(page[-1].open_time_ms, interval)
            if next_cursor <= cursor:
                raise RuntimeError("REST backfill cursor did not advance")
            cursor = next_cursor
            if len(page) < limit:
                break
        return candles

    def _http_get_json(self, url: str, params: dict[str, object]) -> list[list[object]]:
        self.rate_limiter.acquire(weight=2)
        query_string = parse.urlencode(params)
        full_url = f"{url}?{query_string}"
        retries = 0
        while True:
            req = request.Request(
                full_url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "QuantCrypt/0.1",
                },
            )
            try:
                with request.urlopen(req, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except error.HTTPError as exc:
                if exc.code in {418, 429}:
                    retry_after = exc.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else min(60.0, 2**retries)
                    time.sleep(delay)
                    retries += 1
                    continue
                if 500 <= exc.code <= 599 and retries < 5:
                    time.sleep(min(30.0, 2**retries))
                    retries += 1
                    continue
                raise


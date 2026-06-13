from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from typing import Any

from ..models import OHLCVCandle


ClosedCandleHandler = Callable[[OHLCVCandle], Any]


class BinanceWebSocketCollector:
    def __init__(
        self,
        *,
        base_url: str = "wss://data-stream.binance.vision/ws",
        market_type: str = "spot",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.market_type = market_type

    def stream_name(self, symbol: str, interval: str) -> str:
        return f"{symbol.lower()}@kline_{interval}"

    def parse_message(self, message: str) -> OHLCVCandle | None:
        payload = json.loads(message)
        event = payload.get("data", payload)
        kline = event.get("k")
        if not isinstance(kline, dict):
            return None
        candle = OHLCVCandle.from_ws_payload(
            kline,
            market_type=self.market_type,
            source="websocket",
        )
        if not candle.is_closed:
            return None
        return candle

    async def collect_live_klines(
        self,
        *,
        symbol: str,
        interval: str,
        on_closed_candle: ClosedCandleHandler,
        stop_after: int | None = None,
        max_reconnects: int = 5,
    ) -> int:
        import websockets

        received = 0
        reconnects = 0
        url = f"{self.base_url}/{self.stream_name(symbol, interval)}"
        while True:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=60) as websocket:
                    async for message in websocket:
                        candle = self.parse_message(message)
                        if candle is None:
                            continue
                        result = on_closed_candle(candle)
                        if inspect.isawaitable(result):
                            await result
                        received += 1
                        reconnects = 0
                        if stop_after is not None and received >= stop_after:
                            return received
            except Exception:
                reconnects += 1
                if reconnects > max_reconnects:
                    raise
                await asyncio.sleep(min(30.0, 2**reconnects))


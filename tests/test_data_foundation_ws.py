import json

from quantcrypt.data_foundation.collectors.binance_ws_collector import BinanceWebSocketCollector


def test_ws_parser_only_emits_closed_klines() -> None:
    collector = BinanceWebSocketCollector()

    open_message = json.dumps(
        {
            "e": "kline",
            "k": {
                "t": 0,
                "T": 59_999,
                "s": "BTCUSDT",
                "i": "1m",
                "o": "100.0",
                "c": "101.0",
                "h": "102.0",
                "l": "99.0",
                "v": "10.0",
                "q": "1000.0",
                "n": 10,
                "V": "4.0",
                "Q": "400.0",
                "x": False,
            },
        }
    )
    closed_message = json.dumps(
        {
            "e": "kline",
            "k": {
                "t": 60_000,
                "T": 119_999,
                "s": "BTCUSDT",
                "i": "1m",
                "o": "100.0",
                "c": "101.0",
                "h": "102.0",
                "l": "99.0",
                "v": "10.0",
                "q": "1000.0",
                "n": 10,
                "V": "4.0",
                "Q": "400.0",
                "x": True,
            },
        }
    )

    assert collector.parse_message(open_message) is None
    assert collector.parse_message(closed_message).open_time_ms == 60_000


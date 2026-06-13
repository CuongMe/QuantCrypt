from quantcrypt.data_foundation.collectors.binance_rest_collector import BinanceRestCollector


def _rest_row(open_time_ms: int) -> list[object]:
    return [
        open_time_ms,
        "100.0",
        "110.0",
        "90.0",
        "105.0",
        "12.0",
        open_time_ms + 59_999,
        "1260.0",
        25,
        "6.0",
        "630.0",
        "0",
    ]


def test_rest_backfill_paginates_until_range_end() -> None:
    responses = {
        0: [_rest_row(0), _rest_row(60_000)],
        120_000: [_rest_row(120_000)],
    }

    def http_get_json(url: str, params: dict[str, object]) -> list[list[object]]:
        assert url.endswith("/api/v3/klines")
        return responses.get(int(params["startTime"]), [])

    collector = BinanceRestCollector(http_get_json=http_get_json)
    candles = collector.backfill_klines(
        symbol="BTCUSDT",
        interval="1m",
        start_time_ms=0,
        end_time_ms=180_000,
        limit=2,
    )

    assert [candle.open_time_ms for candle in candles] == [0, 60_000, 120_000]


from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections.abc import Callable
from datetime import date, timedelta
from urllib import request

from ..models import OHLCVCandle
from ..timeframes import interval_to_data_vision


BytesGetter = Callable[[str], bytes]


class BinanceBulkDownloader:
    def __init__(
        self,
        *,
        base_url: str = "https://data.binance.vision/data",
        market_type: str = "spot",
        http_get_bytes: BytesGetter | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.market_type = market_type
        self.http_get_bytes = http_get_bytes or self._http_get_bytes

    def download_monthly_klines(
        self,
        *,
        symbol: str,
        interval: str,
        year: int,
        month: int,
    ) -> list[OHLCVCandle]:
        interval_slug = interval_to_data_vision(interval)
        filename = f"{symbol}-{interval_slug}-{year:04d}-{month:02d}.zip"
        relative_path = f"{self.market_type}/monthly/klines/{symbol}/{interval_slug}/{filename}"
        return self._download_archive(relative_path, symbol=symbol, interval=interval)

    def download_daily_klines(
        self,
        *,
        symbol: str,
        interval: str,
        day: date,
    ) -> list[OHLCVCandle]:
        interval_slug = interval_to_data_vision(interval)
        filename = f"{symbol}-{interval_slug}-{day.isoformat()}.zip"
        relative_path = f"{self.market_type}/daily/klines/{symbol}/{interval_slug}/{filename}"
        return self._download_archive(relative_path, symbol=symbol, interval=interval)

    def download_date_range(
        self,
        *,
        symbol: str,
        interval: str,
        start_date: date,
        end_date: date,
    ) -> list[OHLCVCandle]:
        cursor = start_date
        candles: list[OHLCVCandle] = []
        while cursor <= end_date:
            month_start = cursor.replace(day=1)
            next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_end = next_month - timedelta(days=1)
            if cursor == month_start and month_end <= end_date:
                candles.extend(
                    self.download_monthly_klines(
                        symbol=symbol,
                        interval=interval,
                        year=cursor.year,
                        month=cursor.month,
                    )
                )
                cursor = month_end + timedelta(days=1)
                continue
            candles.extend(self.download_daily_klines(symbol=symbol, interval=interval, day=cursor))
            cursor += timedelta(days=1)
        return candles

    def _download_archive(
        self,
        relative_path: str,
        *,
        symbol: str,
        interval: str,
    ) -> list[OHLCVCandle]:
        archive_bytes = self.http_get_bytes(f"{self.base_url}/{relative_path}")
        checksum_bytes = self.http_get_bytes(f"{self.base_url}/{relative_path}.CHECKSUM")
        self._verify_checksum(archive_bytes, checksum_bytes.decode("utf-8"))
        return self._parse_archive(archive_bytes, symbol=symbol, interval=interval)

    def _verify_checksum(self, archive_bytes: bytes, checksum_text: str) -> None:
        expected_checksum = checksum_text.strip().split()[0]
        actual_checksum = hashlib.sha256(archive_bytes).hexdigest()
        if actual_checksum != expected_checksum:
            raise RuntimeError("Binance Data Vision checksum verification failed")

    def _parse_archive(
        self,
        archive_bytes: bytes,
        *,
        symbol: str,
        interval: str,
    ) -> list[OHLCVCandle]:
        candles: list[OHLCVCandle] = []
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            for file_name in archive.namelist():
                with archive.open(file_name, "r") as handle:
                    reader = csv.reader(io.TextIOWrapper(handle, encoding="utf-8"))
                    for row in reader:
                        if not row:
                            continue
                        candles.append(
                            OHLCVCandle.from_rest_row(
                                row,
                                symbol=symbol,
                                interval=interval,
                                market_type=self.market_type,
                                source="bulk",
                            )
                        )
        return candles

    def _http_get_bytes(self, url: str) -> bytes:
        req = request.Request(url, headers={"User-Agent": "QuantCrypt/0.1"})
        with request.urlopen(req, timeout=60) as response:
            return response.read()


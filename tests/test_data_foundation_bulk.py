import hashlib
import io
import zipfile

from quantcrypt.data_foundation.collectors.binance_bulk_downloader import BinanceBulkDownloader


def test_bulk_downloader_verifies_checksum_and_normalizes_microseconds() -> None:
    csv_body = (
        "1735689600000000,100.0,110.0,90.0,105.0,10.0,"
        "1735689659999999,1000.0,25,4.0,400.0,0\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("BTCUSDT-1m-2025-01.csv", csv_body)
    archive_bytes = buffer.getvalue()
    checksum_bytes = f"{hashlib.sha256(archive_bytes).hexdigest()}  BTCUSDT-1m-2025-01.zip".encode("utf-8")

    def http_get_bytes(url: str) -> bytes:
        if url.endswith(".CHECKSUM"):
            return checksum_bytes
        return archive_bytes

    downloader = BinanceBulkDownloader(http_get_bytes=http_get_bytes)
    candles = downloader.download_monthly_klines(symbol="BTCUSDT", interval="1m", year=2025, month=1)

    assert len(candles) == 1
    assert candles[0].open_time_ms == 1_735_689_600_000
    assert candles[0].close_time_ms == 1_735_689_659_999


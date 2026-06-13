from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROJECT_ROOT / "runtime"
SQLITE_DIR = RUNTIME_DIR / "sqlite"
FAISS_DIR = RUNTIME_DIR / "faiss"

DEFAULT_DB_PATH = SQLITE_DIR / "quantcrypt.sqlite3"
DEFAULT_FAISS_INDEX_PATH = FAISS_DIR / "quantcrypt_memory.faiss"


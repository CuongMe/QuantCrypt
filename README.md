# QuantCrypt

Phase 0 of the project starts here.

As of 2026-06-07, this workspace is not an application yet. It contains a Python virtual environment and one local key file, but no source code, no package structure, and no git history.

## Current State

- Python runtime: `3.11.9`
- Installed packages suggest the intended direction: `ccxt`, `python_binance`, `pandas`, `scikit-learn`, `streamlit`, `transformers`, `sentence-transformers`, `torch`
- No implementation files are present yet
- Secrets must not be stored in tracked plaintext files

## Working Rules

- Record each step in [docs/worklog.md](docs/worklog.md)
- Update the system view in [docs/architecture.md](docs/architecture.md)
- Keep secrets out of git-tracked files

## Next Step

Choose the first executable slice of the trading system and implement it incrementally.


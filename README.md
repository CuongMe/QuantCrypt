# QuantCrypt

QuantCrypt is a local-first multi-agent crypto trading system built around four Layer 1 agents, a LangGraph supervisor, Binance market-data ingestion, and an AI engineering layer for reports, memory, and retrieval.

## Current Runtime

- `Data Foundation Node` for Binance REST, WebSocket, and Data Vision ingestion
- `Database` storage for market candles, reports, and memory artifacts
- `AI Engineering Layer` for evidence building, memory construction, and Agentic RAG
- `Supervisor Node` implemented as a LangGraph state machine
- `Layer 1` agents: `Analyst`, `Researcher`, `Trader`, and `Risk Management`
- Local Ollama runtime using `gemma4:12b` through LangChain `ChatOllama`
- Streamlit dashboard with `Backtest`, `Paper Trading`, and `Live Trading` demo modes

## Current State

- Python runtime: `3.11.9`
- The supervisor can run from SQL-backed market evidence instead of only synthetic inputs
- The LLM boundary uses LangChain structured outputs with Pydantic validation
- The orchestration layer uses LangGraph shared state instead of a custom loop
- `Backtest` is read-only and does not write reports or memories
- `Paper Trading` persists reports and memory artifacts
- `Live Trading` remains `demo account only`
- Secrets must not be stored in tracked plaintext files

## Local LLM Runtime

The current implementation targets local Ollama with `gemma4:12b`.

1. Install and run Ollama.
2. Pull the model:

```powershell
ollama pull gemma4:12b
```

3. The repo includes:

- [.env.example](.env.example)
- local `.env` with the same defaults

4. Optionally override defaults:

```powershell
$env:OLLAMA_MODEL="gemma4:12b"
$env:OLLAMA_BASE_URL="http://localhost:11434"
$env:QUANTCRYPT_DB_PATH="runtime/sqlite/quantcrypt.sqlite3"
$env:QUANTCRYPT_FAISS_INDEX_PATH="runtime/faiss/quantcrypt_memory.faiss"
```

The code loads `.env` automatically and uses LangChain `ChatOllama` against the local Ollama runtime.

## Implemented Nodes

- `Data Foundation Node`: [quantcrypt/data_foundation/data_node.py](quantcrypt/data_foundation/data_node.py)
- `AI Engineering Node`: [quantcrypt/ai_engineering/ai_node.py](quantcrypt/ai_engineering/ai_node.py)
- `Supervisor Node`: [quantcrypt/supervisor.py](quantcrypt/supervisor.py)
- `Analyst Agent`: [quantcrypt/agents/analyst.py](quantcrypt/agents/analyst.py)
- `Researcher Agent`: [quantcrypt/agents/researcher.py](quantcrypt/agents/researcher.py)
- `Trader Agent`: [quantcrypt/agents/trader.py](quantcrypt/agents/trader.py)
- `Risk Management Agent`: [quantcrypt/agents/risk.py](quantcrypt/agents/risk.py)
- `Ollama LLM Adapter`: [quantcrypt/llm.py](quantcrypt/llm.py)
- Shared models: [quantcrypt/models.py](quantcrypt/models.py)

## Data Foundation

The Binance ingestion module lives under:

```text
quantcrypt/
`-- data_foundation/
    |-- data_node.py
    |-- storage.py
    |-- validator.py
    `-- collectors/
        |-- binance_rest_collector.py
        |-- binance_ws_collector.py
        |-- binance_bulk_downloader.py
        `-- binance_rate_limiter.py
```

Current capabilities:

- REST kline backfill from Binance public market data REST
- SQLite `clean_ohlcv` table with idempotent upserts
- Candle validation and missing-candle repair
- WebSocket live kline collector for closed candles
- Data Vision bulk downloader with checksum verification

## AI Engineering Layer

The AI engineering module lives under:

```text
quantcrypt/
`-- ai_engineering/
    |-- ai_node.py
    |-- evidence.py
    |-- reports.py
    |-- memory_builder.py
    |-- rag.py
    |-- faiss_store.py
    |-- store.py
    `-- embeddings.py
```

Current capabilities:

- SQL-backed structured market evidence from `clean_ohlcv`
- Decision reports and per-agent report persistence
- Memory artifact construction from decisions and agent outputs
- FAISS vector indexing for summarized memory artifacts
- Agentic RAG that combines structured database evidence with semantic memory retrieval
- End-to-end supervisor execution from `symbol + interval`

## Runtime Storage

QuantCrypt uses dedicated runtime folders:

- SQLite database: [runtime/sqlite](/d:/QuantCrypt/runtime/sqlite)
- FAISS indexes: [runtime/faiss](/d:/QuantCrypt/runtime/faiss)

Default files:

- SQLite DB: `runtime/sqlite/quantcrypt.sqlite3`
- FAISS index: `runtime/faiss/quantcrypt_memory.faiss`

## Dashboard

The current dashboard is a Streamlit control surface for the implemented architecture:

- `Backtest`
- `Paper Trading`
- `Live Trading`

Current behavior:

- `Backtest` is read-only and does not persist reports or memory artifacts
- `Paper Trading` persists supervisor reports and memory artifacts
- `Live Trading` is still `demo account only` and does not place exchange orders
- `Run` and `Stop` control the active dashboard execution loop
- `Live Monitor` shows component health, recent agent activity, and alerts including Ollama connectivity failures

Run the dashboard:

```powershell
.\.venv\Scripts\streamlit.exe run dashboard_app.py
```

## Test

Run:

```powershell
.\.venv\Scripts\pytest.exe -q
```

## Working Rules

- Record each step in [docs/worklog.md](docs/worklog.md)
- Update the system view in [docs/architecture.md](docs/architecture.md)
- Keep secrets out of git-tracked files

## Next Step

Add explicit execution-state transitions for `Backtest`, `Paper Trading`, and `Live Trading` so the dashboard can drive a more formal runtime state machine.

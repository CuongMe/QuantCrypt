# System Architecture

This is the initial target architecture for the Crypto Trading AI Agent. It is a planning diagram, not an implementation report yet.

```mermaid
flowchart LR
    Market["Market Data Sources"] --> Ingest["Data Ingestion"]
    News["News / External Signals"] --> Ingest
    Ingest --> Features["Feature Engineering / Context"]
    Features --> Strategy["Strategy / AI Decision Layer"]
    Strategy --> Risk["Risk Controls"]
    Risk --> Execution["Execution Layer"]
    Execution --> Portfolio["Portfolio State"]
    Portfolio --> Journal["Trade Journal / Metrics"]
    Journal --> Strategy
```

## Notes

- The first implementation should stay in `paper trading` mode.
- Risk control must exist before live execution is allowed.
- The architecture diagram should be updated whenever a new subsystem becomes real code.


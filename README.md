# GoGmailAnalytics

Turn years of Gmail history into a structured personal/professional
relationship-intelligence dataset. Local-first, privacy-conscious, and
modular:

```
Gmail account(s) → ingestion → DuckDB → contact resolution
    → categorization → relationship analytics
    → Google Sheets / Excel / dashboard
```

One mailbox becomes a queryable model of your network: who you talk to,
how often, about what, which relationships are thriving, which are going
dormant, and who you should follow up with.

## Features

- **Historical + incremental ingestion** — full mailbox scans with resume,
  date ranges, label/query filters, rate-limit backoff, and incremental
  mode that only fetches new mail.
- **Contact resolution** — one person is not one email address. Addresses
  are clustered into person records (normalized email + display-name /
  local-part matching); low-confidence pairs are never auto-merged, and
  every merge records its confidence and reason.
- **Categorization** — controlled taxonomies (relationship category,
  subcategory, strength 1–6, lifecycle, communication type) with a
  deterministic rule-based categorizer; optional LLM providers behind a
  common interface.
- **Relationship analytics** — communication frequency from historical
  intervals, recency, an explainable 0–100 health score
  (30% recency + 25% frequency + 20% strength + 15% importance +
  10% responsiveness), and follow-up intelligence.
- **Organization, career & topic intelligence** — domain-based org
  extraction, career signals (recruiters, opportunities), keyword topics.
- **Network analysis** — people/organization graph with centrality via
  NetworkX.
- **Outputs** — Google Sheets upserts on stable IDs (never duplicates),
  formatted Excel workbook, DuckDB for ad-hoc analysis, dashboard data
  prep (Streamlit optional), semantic-search stub (optional stack).
- **Privacy by default** — read-only Gmail scope, no body storage, AI
  off by default and restricted to allow-listed fields when enabled.

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 1. Point config.yaml at your account(s)
# 2. Verify access
.venv/bin/python main.py auth

# 3. Scan history (resumable; newest mail first)
.venv/bin/python main.py scan --account personal --from 2010-01-01

# 4. Build the analytical model
.venv/bin/python main.py analyze --account personal

# 5. Publish
.venv/bin/python main.py export-excel
.venv/bin/python main.py sync-sheets --spreadsheet <YOUR_SHEET_ID>
```

Later runs only fetch what's new:

```bash
.venv/bin/python main.py scan --account personal --incremental
.venv/bin/python main.py analyze --account personal
.venv/bin/python main.py sync-sheets
```

## CLI reference

| Command | What it does |
|---|---|
| `auth` | Verify Gmail connectivity for enabled accounts |
| `scan --account NAME [--from DATE] [--to DATE] [--incremental] [--max N]` | Ingest message metadata (resumable) |
| `analyze --account NAME` | Resolve contacts, categorize, score, load DuckDB |
| `sync-sheets [--spreadsheet ID]` | Upsert results to Google Sheets on stable IDs |
| `export-excel [--output PATH]` | Formatted workbook (`output/`) |
| `dashboard [--port N]` | Dashboard datasets (Streamlit optional) |
| `search "query"` | Semantic search (optional embeddings stack) |

## Configuration

`config.yaml` holds accounts, privacy, ingestion, analytics, AI and
Sheets settings; `${VAR:-default}` expands from the environment. See
[`docs/CONFIGURATION.md`](docs/CONFIGURATION.md). Secrets go in `.env`
(see `.env.example`) — never in `config.yaml`.

## Privacy & security

Read [`docs/PRIVACY.md`](docs/PRIVACY.md) before running against a real
mailbox. Short version: read-only scope, metadata-first, no bodies stored,
AI optional and field-restricted, exclusion lists for labels/addresses/
domains, and `data/` is git-ignored so mailbox contents never land in
version control.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the module map,
data model, and the transport abstraction (connector vs direct OAuth).

## Data dictionary

[`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) documents every
table and column: description, type, source, and calculation.

## Testing

```bash
.venv/bin/python -m pytest tests/ -q
```

Tests use mock Gmail payloads — no real account needed.

## Project layout

```
├── main.py                 # CLI entry
├── config.yaml             # your local configuration (not committed with secrets)
├── src/gmail_intel/        # the framework
│   ├── auth/               # transport abstraction (connector | OAuth)
│   ├── gmail/              # thin Gmail client
│   ├── ingestion/          # resumable scan engine + state
│   ├── parsing/            # payload → normalized email record
│   ├── database/           # DuckDB schema + upserts
│   ├── contacts/           # entity resolution
│   ├── categorization/     # taxonomies + rule/AI categorizers
│   ├── analytics/          # frequency, health score, follow-ups
│   ├── nlp/                # keyword topics, regex entities
│   ├── organizations/      # domain-based org intelligence
│   ├── career/             # career signals
│   ├── relationships/      # network graph
│   ├── embeddings/         # semantic search (optional)
│   ├── sheets/             # Google Sheets upserts
│   ├── exports/            # Excel workbook
│   └── dashboard/          # dashboard datasets
├── tests/
├── notebooks/              # exploratory analysis starters
└── docs/
```

## Requirements

Python 3.11+. Core: `duckdb`, `pandas`, `pyarrow`, `openpyxl`,
`pyyaml`, `requests`, `python-dateutil`, `plotly`, `networkx`.
Optional: `spacy`/`nltk` (NLP), `sentence-transformers`/`chromadb`
(semantic search), `streamlit` (dashboard).

## License

MIT — see [LICENSE](LICENSE).

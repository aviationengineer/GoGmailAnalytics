# Architecture

## Module map

```
gmail_intel/
├── config/          YAML + env loading, privacy defaults, project paths
├── auth/            GmailTransport ABC
│                    ├── ConnectorTransport  host runtime's connected Gmail
│                    └── OAuthTransport       direct google-api-python-client
│                                            OAuth 2.0 (for other runtimes)
├── gmail/           GmailClient: list/get/search/profile/labels over a transport
├── ingestion/       ScanEngine: paged ID discovery, resumable metadata fetch,
│                    incremental mode (newest-first, stop at first known id),
│                    exponential backoff, per-account JSON state
├── parsing/         Gmail payload → normalized email dict; thread summaries.
│                    Bodies decoded only when store_body=True.
├── database/        DuckDB: schema + upserts. Stable IDs everywhere, so
│                    reruns never duplicate.
├── contacts/        Union-find entity resolution:
│                      1. exact normalized email (gmail dots/plus folded)
│                      2. same display name + same local-part stem
│                    Low-confidence pairs are never merged. Every merge stores
│                    merge_confidence + merge_reason.
├── categorization/  Controlled taxonomies + CategorizationProvider ABC.
│                    RuleBasedCategorizer (labels, sender patterns, domains)
│                    works with zero dependencies. OpenAI/Local/Gemini
│                    providers plug in; the system runs fully without any LLM.
├── analytics/       frequency bands from historical intervals, recency,
│                    explainable health score, follow-up rules
├── nlp/             keyword topics, regex entities (orgs, emails, phones);
│                    spaCy NER plugs in when installed
├── organizations/   domain → organization rollups
├── career/          recruiter / opportunity signals
├── relationships/   people+org graph, degree/betweenness via NetworkX
├── embeddings/      semantic-search stub (sentence-transformers + ChromaDB)
├── sheets/          Google Sheets upserts on ID columns
├── exports/         formatted Excel workbook
├── dashboard/       data_for_dashboard() datasets; Streamlit optional
├── pipeline/        analyze(): raw → DuckDB → contacts → everything
└── cli/             argparse front end (main.py)
```

## Data flow

```
scan            → data/raw/meta_<account>.jsonl   (append-only, resumable)
analyze         → data/processed/gmail_intel.duckdb
sync-sheets     → Google Sheets (upsert on stable IDs)
export-excel    → output/gmail_relationship_intelligence.xlsx
```

## Key design decisions

- **Transport abstraction.** Gmail access differs by runtime. `GmailTransport`
  is the seam: `ConnectorTransport` shells out to the host's workspace CLI
  (override with `GMAIL_INTEL_GWS_CLI`), while `OAuthTransport` is the
  documented path for direct `google-api-python-client` OAuth deployments.
  Nothing above `gmail/` knows which is in use.
- **Stable IDs.** Contacts are `C000001…` by message-count rank; messages,
  threads, orgs keep provider IDs. Sheets/DB loads are upserts, so
  incremental runs only add or refresh.
- **Metadata-first.** Relationship analytics need sender/recipients/date/
  subject/frequency — not bodies. Bodies stay off unless explicitly enabled.
- **No silent merges.** Entity resolution merges only on strong evidence and
  says why; ambiguous pairs stay split for the user to review.
- **AI is a plugin, not a dependency.** The rule-based categorizer covers
  the core loop; LLM providers add nuance when available and allowed.

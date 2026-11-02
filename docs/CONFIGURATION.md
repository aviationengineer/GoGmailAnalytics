# Configuration

`config.yaml` is the single configuration file. `${VAR:-default}` expands
from the environment. Copy it per environment; never commit secrets.

## gmail

- `transport`: `connector` (host runtime's connected Gmail; no secrets) or
  `oauth` (direct Google OAuth 2.0 via client-secrets/token files — see
  `.env.example` and `auth.OAuthTransport`).
- `accounts`: list of `{name, account_id, enabled}`. Names are used on the
  CLI (`--account personal`). For the connector transport, find the
  `account_id` with `$GMAIL_INTEL_GWS_CLI gmail accounts`.
- `scope`: keep the read-only default.

## processing

- `store_body`: fetch and store full bodies. Default `false`.
- `store_snippet`: keep Gmail snippets (short previews). Default `true`.
- `process_attachments`: reserved for attachment inventory. Default `false`.
- `max_results_per_page`: Gmail list page size (max 500).

## privacy

See [PRIVACY.md](PRIVACY.md). `exclude_labels` / `exclude_addresses` /
`exclude_domains` are applied during ingestion.

## ingestion

- `default_query`: Gmail search query for scans. The default drops bulk
  categories (`-category:promotions -category:social -category:forums`).
  Narrow with `--from`/`--to` on the CLI.
- `request_sleep_seconds` / `max_retries`: politeness and backoff.

## analytics

Toggles for relationship scoring, network analysis, and topic modeling
(topic modeling needs the optional NLP stack).

## ai

`enabled: false` by default. `provider`: `openai` | `local` | `gemini`;
`model` is provider-specific. The OpenAI provider calls a connector
helper; override its path with `GMAIL_INTEL_OPENAI_HELPER`.

## google_sheets

`enabled` + `spreadsheet_id` (or `GOOG_SHEETS_SPREADSHEET_ID`). `sync-sheets`
upserts every table on its stable ID column: existing rows update in
place, new rows append, reruns never duplicate.

## database

`path`: local DuckDB file. Delete it to rebuild from raw (no rescan needed
as long as `data/raw/` is intact).

## Environment variables

| Variable | Purpose |
|---|---|
| `GMAIL_INTEL_GWS_CLI` | Workspace-connector CLI path (default `/opt/hatch/bin/hatch_gws_cli`) |
| `GMAIL_INTEL_OPENAI_HELPER` | OpenAI connector helper script path |
| `GOOG_SHEETS_SPREADSHEET_ID` | Default Sheets target |
| `GMAIL_CLIENT_SECRETS_FILE` / `GMAIL_TOKEN_FILE` | Direct-OAuth deployment |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | AI providers (optional) |

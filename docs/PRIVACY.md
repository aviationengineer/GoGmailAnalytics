# Privacy & Security

## Principles

1. **Read-only Gmail access.** The default scope is
   `https://www.googleapis.com/auth/gmail.readonly`. The framework never
   sends, deletes, or modifies mail, and there is no code path that could.
2. **Metadata-first.** Contact intelligence runs on sender, recipients,
   date, subject, labels, and frequency. Email bodies are not fetched in
   full mode and not stored by default (`privacy.store_email_body: false`).
3. **AI is optional and fenced.** `privacy.enable_ai` defaults to false.
   When enabled, only allow-listed fields
   (`privacy.allowed_ai_fields`: subject, snippet, extracted topics) may
   reach a model. Bodies, attachments, and the raw mailbox never do.
4. **No secrets in code or logs.** Account credentials live with the
   transport (host connector or local OAuth token file). API keys come
   from the environment. Logs never include bodies, tokens, or keys.
5. **Local-first storage.** The analytical database is a local DuckDB
   file. `data/` is git-ignored: mailbox contents never belong in version
   control.
6. **Exclusion lists.** `privacy.exclude_labels`, `exclude_addresses`,
   and `exclude_domains` drop sensitive mail before it is stored.

## What's stored where

| Location | Contents | Sensitivity |
|---|---|---|
| `data/raw/meta_<account>.jsonl` | Per-message metadata (headers, snippet) | Your mailbox |
| `data/processed/gmail_intel.duckdb` | Normalized analytical model | Derived from mailbox |
| `data/processed/scan_state.json` | Ingestion watermarks per account | Operational |
| Google Sheets (optional target) | Published analytical tables | Whatever you sync |
| Git repo | Code, docs, config templates only | None of your mail |

## Before you run

- Review `config.yaml` privacy settings.
- Keep `.env` out of version control (see `.gitignore`).
- If you enable AI, confirm your provider's data-retention terms suit
  mailbox metadata.
- The `mask_pii` option masks email local-parts in logs and exports.

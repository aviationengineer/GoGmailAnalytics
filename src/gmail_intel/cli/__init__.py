"""CLI: gmail-intel auth | scan | analyze | categorize | sync-sheets |
export-excel | dashboard | search"""
from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-5s %(name)s %(message)s")


def _ctx(args):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "..", "src"))
    from gmail_intel.config import Config
    cfg = Config.load(args.config) if args.config else Config.load()
    return cfg


def cmd_auth(args):
    cfg = _ctx(args)
    from gmail_intel.auth import make_transport
    for acct in cfg.enabled_accounts():
        t = make_transport(cfg.get("gmail", "transport", default="connector"),
                           account_id=acct.get("account_id", ""))
        print(f"{acct['name']}: {t.profile_email()} (connected)")
    return 0


def _engine_for(cfg, account_name: str):
    from gmail_intel.auth import make_transport
    from gmail_intel.gmail import GmailClient
    from gmail_intel.ingestion import ScanEngine, ScanState
    acct = next(a for a in cfg.enabled_accounts() if a["name"] == account_name)
    transport = make_transport(cfg.get("gmail", "transport", default="connector"),
                               account_id=acct.get("account_id", ""))
    client = GmailClient(transport)
    state = ScanState(cfg.data_path("processed", "scan_state.json"))
    return ScanEngine(
        client, account_name, state,
        raw_dir=cfg.data_path("raw"),
        query=cfg.get("ingestion", "default_query", default=""),
        sleep=cfg.get("ingestion", "request_sleep_seconds", default=0.05),
        max_retries=cfg.get("ingestion", "max_retries", default=5),
        store_body=cfg.get("privacy", "store_email_body", default=False)), client


def cmd_scan(args):
    cfg = _ctx(args)
    for acct in cfg.enabled_accounts():
        if args.account and acct["name"] != args.account:
            continue
        engine, _ = _engine_for(cfg, acct["name"])
        summary = engine.scan(date_from=args.from_ or "", date_to=args.to or "",
                              incremental=args.incremental,
                              max_messages=args.max or 0)
        print(f"[{acct['name']}] {summary}")
    return 0


def cmd_analyze(args):
    cfg = _ctx(args)
    from gmail_intel.database import Database
    from gmail_intel.pipeline import analyze
    db = Database(cfg.data_path("processed", "gmail_intel.duckdb"))
    try:
        for acct in cfg.enabled_accounts():
            if args.account and acct["name"] != args.account:
                continue
            _, client = _engine_for(cfg, acct["name"])
            summary = analyze(acct["name"], client.profile_email(),
                              cfg.data_path("raw"), db, cfg)
            print(f"[{acct['name']}] "
                  f"{summary['emails']} emails, {summary['contacts']} contacts, "
                  f"{summary['follow_ups']} follow-ups")
    finally:
        db.close()
    return 0


def cmd_sync_sheets(args):
    cfg = _ctx(args)
    from gmail_intel.database import Database
    from gmail_intel.sheets import SheetsSync
    sheet_id = args.spreadsheet or cfg.get("google_sheets", "spreadsheet_id")
    if not sheet_id:
        print("no spreadsheet id: pass --spreadsheet or set GOOG_SHEETS_SPREADSHEET_ID")
        return 2
    db = Database(cfg.data_path("processed", "gmail_intel.duckdb"))
    try:
        total = SheetsSync(sheet_id).sync_all(db)
    finally:
        db.close()
    for sheet, stats in total.items():
        print(f"{sheet}: {stats}")
    return 0


def cmd_export_excel(args):
    cfg = _ctx(args)
    from gmail_intel.database import Database
    from gmail_intel.exports import export_excel
    out = args.output or os.path.join(cfg.project_root, "output",
                                      "gmail_relationship_intelligence.xlsx")
    db = Database(cfg.data_path("processed", "gmail_intel.duckdb"))
    try:
        path = export_excel(db, out)
    finally:
        db.close()
    print(f"wrote {path}")
    return 0


def cmd_dashboard(args):
    cfg = _ctx(args)
    from gmail_intel.dashboard import data_for_dashboard, run_app
    from gmail_intel.database import Database
    db = Database(cfg.data_path("processed", "gmail_intel.duckdb"))
    try:
        data = data_for_dashboard(db)
    finally:
        db.close()
    print("overview:", data["overview"])
    run_app(cfg.data_path("processed", "gmail_intel.duckdb"), port=args.port)
    return 0


def cmd_search(args):
    print("semantic search needs the optional embeddings stack "
          "(sentence-transformers + chromadb); not installed")
    return 2


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="gmail-intel",
                                 description="Gmail relationship intelligence")
    ap.add_argument("--config", help="path to config.yaml")
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="verify Gmail connectivity")
    p = sub.add_parser("scan", help="scan Gmail history")
    p.add_argument("--account", help="account name from config")
    p.add_argument("--from", dest="from_", help="start date YYYY-MM-DD")
    p.add_argument("--to", dest="to", help="end date YYYY-MM-DD")
    p.add_argument("--incremental", action="store_true")
    p.add_argument("--max", type=int, default=0, help="max messages (0 = all)")
    p.add_argument("--query", help="extra Gmail search query (reserved)")

    p = sub.add_parser("analyze", help="build contacts/analytics in DuckDB")
    p.add_argument("--account", help="account name from config")

    p = sub.add_parser("sync-sheets", help="upsert results to Google Sheets")
    p.add_argument("--spreadsheet", help="spreadsheet id")

    p = sub.add_parser("export-excel", help="write formatted Excel workbook")
    p.add_argument("--output", help="output path")

    p = sub.add_parser("dashboard", help="open Streamlit dashboard")
    p.add_argument("--port", type=int, default=8501)

    p = sub.add_parser("search", help="semantic search over history")
    p.add_argument("query", nargs="?", default="")

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"auth": cmd_auth, "scan": cmd_scan, "analyze": cmd_analyze,
                "sync-sheets": cmd_sync_sheets, "export-excel": cmd_export_excel,
                "dashboard": cmd_dashboard, "search": cmd_search}
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())

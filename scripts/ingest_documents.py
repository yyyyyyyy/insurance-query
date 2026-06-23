#!/usr/bin/env python3
"""CLI: Import PDF/TXT into knowledge_pack/chunks/ (manual or fetched files)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge.ingestion.policy_ingest import (  # noqa: E402
    OUTPUT_PATH,
    init_manifest_from_catalog,
    ingest_all,
    list_ingest_status,
)


def cmd_init(_: argparse.Namespace) -> int:
    entries = init_manifest_from_catalog(overwrite=False)
    print(f"Product manifest: {len(entries)} entries")
    print("Regulation manifest: run `python scripts/fetch_documents.py --init`")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    rows = list_ingest_status()
    if not rows:
        print("No manifest found. Run: python scripts/ingest_documents.py --init")
        return 1
    print(f"{'SCOPE':<12} {'FILE':<38} {'DOC_ID':<12} {'FILE':^5} {'INGESTED':^8} {'CHUNKS':>6}")
    print("-" * 90)
    for r in rows:
        print(
            f"{r['scope']:<12} {r['file']:<38} {r['document_id']:<12} "
            f"{'Y' if r['file_exists'] else 'N':^5} "
            f"{'Y' if r['ingested'] else 'N':^8} {r['chunk_count']:>6}"
        )
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    include_products = args.all or args.products or bool(args.file)
    include_regulations = args.all or args.regulations

    if not include_products and not include_regulations:
        include_products = True
        include_regulations = True

    try:
        results, report = ingest_all(
            files=args.file,
            force=args.force,
            dry_run=args.dry_run,
            include_products=include_products,
            include_regulations=include_regulations,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    for r in results:
        icon = {"success": "OK", "skipped": "SKIP", "error": "ERR"}[r.status]
        detail = f"chunks={r.chunk_count}" if r.chunk_count else r.error
        print(f"[{icon}] {r.entry.file} -> {r.entry.document_id} ({detail})")

    s = report["summary"]
    print(f"\nDone: {s['success']} ingested, {s['skipped']} skipped, {s['error']} errors")
    if args.dry_run:
        print("(dry-run: no files written)")
    elif s["success"] > 0:
        print(f"Output: {OUTPUT_PATH}")
    return 0 if s["error"] == 0 else 1


def cmd_status(_: argparse.Namespace) -> int:
    if OUTPUT_PATH.exists():
        print(json.dumps(_read_meta(), ensure_ascii=False, indent=2))
    else:
        print("No ingested documents yet.")
        print("Place files in policy_documents/ or regulations/documents/, then run --all")
    return 0


def _read_meta() -> dict:
    with open(OUTPUT_PATH, encoding="utf-8") as f:
        return json.load(f).get("meta", {})


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import insurer/regulatory PDF/TXT into retrieval index",
    )
    parser.add_argument("--init", action="store_true",
                        help="Init product manifest from catalog")
    parser.add_argument("--list", action="store_true", help="List import status")
    parser.add_argument("--status", action="store_true", help="Show ingested output meta")
    parser.add_argument("--all", action="store_true",
                        help="Import all available product + regulation files")
    parser.add_argument("--products", action="store_true", help="Import product files only")
    parser.add_argument("--regulations", action="store_true", help="Import regulation files only")
    parser.add_argument("--file", action="append", default=None,
                        help="Import specific manifest file path(s)")
    parser.add_argument("--force", action="store_true", help="Re-import unchanged files")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no write")

    args = parser.parse_args()
    if args.init:
        return cmd_init(args)
    if args.list:
        return cmd_list(args)
    if args.status:
        return cmd_status(args)
    if args.all or args.products or args.regulations or args.file:
        return cmd_ingest(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

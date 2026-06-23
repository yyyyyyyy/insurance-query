#!/usr/bin/env python3
"""CLI: Fetch public documents from insurer official sites and regulators only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge.ingestion.document_fetcher import (  # noqa: E402
    FETCH_REPORT,
    fetch_products,
    fetch_regulations,
    init_regulation_manifest,
    list_fetch_targets,
    sync_product_source_urls,
)


def _print_results(results: list) -> None:
    for r in results:
        icon = {"success": "OK", "skipped": "SKIP", "error": "ERR"}[r.status]
        print(f"[{icon}] {r.target_type}:{r.target_id} — {r.message}")
        if r.output_path:
            print(f"       -> {r.output_path}")


def _split_ids(ids: list[str] | None) -> tuple[list[str], list[str]]:
    product_ids, reg_ids = [], []
    if not ids:
        return product_ids, reg_ids
    for i in ids:
        if i.upper().startswith("REG"):
            reg_ids.append(i.upper())
        elif i.upper().startswith("P"):
            product_ids.append(i.upper())
        else:
            print(f"Unknown id: {i} (use P001 or REG001)", file=sys.stderr)
    return product_ids, reg_ids


def cmd_list(_: argparse.Namespace) -> int:
    info = list_fetch_targets()
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_init(_: argparse.Namespace) -> int:
    sync_product_source_urls()
    manifest = init_regulation_manifest()
    print("Synced product source_url into policy manifest")
    print(f"Regulation manifest: {manifest['meta']['total']} entries")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    product_ids, reg_ids = _split_ids(args.id)
    if args.type == "product":
        product_ids = args.id or []
        reg_ids = []
    elif args.type == "regulation":
        reg_ids = args.id or []
        product_ids = []

    do_products = args.products or args.all or bool(product_ids)
    do_regs = args.regulations or args.all or bool(reg_ids)

    results: list = []
    report: dict = {"summary": {"total": 0, "success": 0, "skipped": 0, "error": 0}, "results": []}

    if do_regs:
        r_results, r_report = fetch_regulations(
            regulation_ids=reg_ids or None, force=args.force, delay_sec=args.delay,
        )
        results.extend(r_results)
        report = r_report

    if do_products:
        p_results, p_report = fetch_products(
            product_ids=product_ids or None, force=args.force, delay_sec=args.delay,
        )
        results.extend(p_results)
        if report["results"]:
            for k in ("total", "success", "skipped", "error"):
                report["summary"][k] += p_report["summary"][k]
            report["results"].extend(p_report["results"])
        else:
            report = p_report

    if not results:
        print("Nothing to fetch. Use --products, --regulations, or --all")
        return 1

    _print_results(results)
    s = report["summary"]
    print(f"\nDone: {s.get('success', 0)} ok, {s.get('skipped', 0)} skipped, {s.get('error', 0)} errors")
    print(f"Report: {FETCH_REPORT}")
    print("\nNext: python scripts/ingest_documents.py --all")
    return 0 if s.get("error", 0) == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch public docs from insurer sites and regulators (allowlist only)",
    )
    parser.add_argument("--init", action="store_true", help="Init fetch manifests")
    parser.add_argument("--list", action="store_true", help="Show fetchable targets")
    parser.add_argument("--products", action="store_true", help="Fetch insurer pages/PDFs")
    parser.add_argument("--regulations", action="store_true", help="Fetch regulatory files")
    parser.add_argument("--all", action="store_true", help="Fetch products + regulations")
    parser.add_argument("--type", choices=["product", "regulation"])
    parser.add_argument("--id", action="append", default=None, help="P001 or REG001")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--delay", type=float, default=1.5)

    args = parser.parse_args()
    if args.list:
        return cmd_list(args)
    if args.init:
        return cmd_init(args)
    if args.all or args.products or args.regulations or args.id:
        return cmd_fetch(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Policy Document Ingestion — PDF/TXT → knowledge_pack/chunks/ingested_documents.json

Workflow:
  1. Place or fetch PDF/TXT into policy_documents/ or regulations/documents/
  2. Register in manifest.json (products: --init; regulations: fetch_documents.py --init)
  3. Run: python scripts/ingest_documents.py --all
  4. Runtime loads via load_ingested_bundle()
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from knowledge.ingestion.naming import product_output_filename
from knowledge.ingestion.pipeline import (
    Chunk,
    ChunkStore,
    DocumentMeta,
    chunk_document,
    extract_text_from_file,
    ingest_document,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
POLICY_DOCS_DIR = ROOT / "knowledge_pack" / "policy_documents"
REG_DOCS_ROOT = ROOT / "knowledge_pack" / "regulations"
MANIFEST_PATH = POLICY_DOCS_DIR / "manifest.json"
REG_MANIFEST_PATH = REG_DOCS_ROOT / "manifest.json"
OUTPUT_PATH = ROOT / "knowledge_pack" / "chunks" / "ingested_documents.json"
REPORT_PATH = ROOT / "knowledge_pack" / "chunks" / "ingestion_report.json"


@dataclass
class ManifestEntry:
    file: str
    document_id: str
    title: str
    document_type: str = "policy_clause"
    product_id: Optional[str] = None
    regulation_id: Optional[str] = None
    enabled: bool = True
    chunk_size: int = 500
    chunk_overlap: int = 50
    notes: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManifestEntry":
        return cls(
            file=data["file"],
            document_id=data["document_id"],
            title=data["title"],
            document_type=data.get("document_type", "policy_clause"),
            product_id=data.get("product_id"),
            regulation_id=data.get("regulation_id"),
            enabled=data.get("enabled", True),
            chunk_size=data.get("chunk_size", 500),
            chunk_overlap=data.get("chunk_overlap", 50),
            notes=data.get("notes", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "document_id": self.document_id,
            "title": self.title,
            "document_type": self.document_type,
            "product_id": self.product_id,
            "regulation_id": self.regulation_id,
            "enabled": self.enabled,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "notes": self.notes,
        }


@dataclass
class IngestResult:
    entry: ManifestEntry
    status: str  # success | skipped | error
    chunk_count: int = 0
    page_count: int = 0
    source_hash: str = ""
    error: str = ""
    document: Optional[Dict[str, Any]] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()[:16]


def load_manifest(path: Optional[Path] = None) -> List[ManifestEntry]:
    manifest_path = path or MANIFEST_PATH
    if not manifest_path.exists():
        return []
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    return [ManifestEntry.from_dict(d) for d in data.get("documents", [])]


def save_manifest(entries: List[ManifestEntry], path: Optional[Path] = None) -> None:
    manifest_path = path or MANIFEST_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "version": "1.0",
            "updated": _now_iso(),
            "description": "将 PDF/TXT 放入 policy_documents/ 目录并在此注册",
        },
        "documents": [e.to_dict() for e in entries],
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def init_manifest_from_catalog(
    *,
    include_regulations: bool = False,
    overwrite: bool = False,
) -> List[ManifestEntry]:
    """Generate manifest entries from products/catalog.json (one slot per product)."""
    if MANIFEST_PATH.exists() and not overwrite:
        logger.info("Manifest already exists: %s (use overwrite=True to regenerate)", MANIFEST_PATH)
        return load_manifest()

    catalog_path = ROOT / "knowledge_pack" / "products" / "catalog.json"
    with open(catalog_path, encoding="utf-8") as f:
        products = json.load(f).get("products", [])

    entries: List[ManifestEntry] = []
    for p in products:
        pid = p["product_id"]
        filename = product_output_filename(p)
        entries.append(ManifestEntry(
            file=filename,
            document_id=f"DOC_{pid}",
            title=f"{p['name']}保险条款",
            document_type="policy_clause",
            product_id=pid,
            enabled=True,
            notes="将官网下载的条款 PDF 命名为上述文件名并放入 policy_documents/",
        ))

    if include_regulations:
        reg_path = ROOT / "knowledge_pack" / "regulations" / "catalog.json"
        with open(reg_path, encoding="utf-8") as f:
            regulations = json.load(f).get("regulations", [])
        for reg in regulations[:10]:
            rid = reg["regulation_id"]
            safe_title = reg["title"][:20].replace("/", "_")
            filename = f"{rid}_{safe_title}.pdf"
            entries.append(ManifestEntry(
                file=filename,
                document_id=f"DOC_{rid}",
                title=reg["title"],
                document_type="regulation",
                regulation_id=rid,
                enabled=False,
                notes=reg.get("source_url", ""),
            ))

    save_manifest(entries)
    return entries


def _resolve_file_path(entry: ManifestEntry, base_dir: Optional[Path] = None) -> Path:
    root = (base_dir or POLICY_DOCS_DIR).resolve()
    path = (root / entry.file).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path traversal rejected for manifest file: {entry.file}") from exc
    if path.exists():
        return path
    if base_dir is None:
        sample_path = POLICY_DOCS_DIR / "samples" / entry.file
        if sample_path.exists():
            return sample_path
        sample_path = POLICY_DOCS_DIR / "samples" / Path(entry.file).name
        if sample_path.exists():
            return sample_path
    return path


def load_regulation_manifest(path: Optional[Path] = None) -> List[ManifestEntry]:
    manifest_path = path or REG_MANIFEST_PATH
    if not manifest_path.exists():
        return []
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    return [ManifestEntry.from_dict(d) for d in data.get("documents", [])]


def chunks_to_document_dict(meta: DocumentMeta, chunks: List[Chunk]) -> Dict[str, Any]:
    doc: Dict[str, Any] = {
        "document_id": meta.document_id,
        "title": meta.title,
        "document_type": meta.document_type,
        "source_path": meta.source_path,
        "file_type": meta.file_type,
        "total_pages": meta.total_pages,
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "content": c.content,
                "clause": c.clause,
                "page": c.page,
                "section_title": c.section_title,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ],
    }
    if meta.product_id:
        doc["product_id"] = meta.product_id
    if meta.extra.get("regulation_id"):
        doc["regulation_id"] = meta.extra["regulation_id"]
    if meta.extra.get("source_hash"):
        doc["source_hash"] = meta.extra["source_hash"]
    return doc


def ingest_manifest_entry(
    entry: ManifestEntry,
    *,
    dry_run: bool = False,
    ignore_enabled: bool = False,
    base_dir: Optional[Path] = None,
) -> IngestResult:
    """Ingest a single manifest entry into DOCUMENT_STORE-compatible dict."""
    if not entry.enabled and not ignore_enabled:
        return IngestResult(entry=entry, status="skipped", error="disabled in manifest")

    file_path = _resolve_file_path(entry, base_dir=base_dir)
    if not file_path.exists():
        return IngestResult(
            entry=entry, status="skipped",
            error=f"file not found: {file_path}",
        )

    try:
        source_hash = _file_hash(file_path)
        if dry_run:
            raw_text, file_info = extract_text_from_file(str(file_path))
            chunks = chunk_document(
                raw_text, entry.document_id,
                chunk_size=entry.chunk_size,
                chunk_overlap=entry.chunk_overlap,
            )
            return IngestResult(
                entry=entry, status="success",
                chunk_count=len(chunks),
                page_count=file_info.get("pages", 1),
                source_hash=source_hash,
            )

        store = ChunkStore()
        extra: Dict[str, Any] = {"source_hash": source_hash}
        if entry.regulation_id:
            extra["regulation_id"] = entry.regulation_id

        meta, chunks = ingest_document(
            file_path=str(file_path),
            document_id=entry.document_id,
            title=entry.title,
            document_type=entry.document_type,
            chunk_store=store,
            embedding_gen=None,
            product_id=entry.product_id,
            chunk_size=entry.chunk_size,
            chunk_overlap=entry.chunk_overlap,
        )
        meta.extra.update(extra)
        document = chunks_to_document_dict(meta, chunks)

        return IngestResult(
            entry=entry, status="success",
            chunk_count=len(chunks),
            page_count=meta.total_pages,
            source_hash=source_hash,
            document=document,
        )
    except Exception as exc:
        logger.exception("Failed to ingest %s", entry.file)
        return IngestResult(entry=entry, status="error", error=str(exc))


def load_ingested_bundle(path: Optional[Path] = None) -> Dict[str, Any]:
    output_path = path or OUTPUT_PATH
    if not output_path.exists():
        return {"meta": {}, "documents": []}
    with open(output_path, encoding="utf-8") as f:
        return json.load(f)


def load_ingested_documents(path: Optional[Path] = None) -> Dict[str, Any]:
    """Backward-compatible alias for load_ingested_bundle."""
    return load_ingested_bundle(path)


def save_ingested_documents(
    documents: List[Dict[str, Any]],
    *,
    report: Optional[Dict[str, Any]] = None,
    path: Optional[Path] = None,
) -> None:
    output_path = path or OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_chunks = sum(len(d.get("chunks", [])) for d in documents)
    payload = {
        "meta": {
            "version": "1.0",
            "ingested_at": _now_iso(),
            "total_documents": len(documents),
            "total_chunks": total_chunks,
            "source": "knowledge_pack/policy_documents/ (PDF/TXT via policy_ingest)",
        },
        "documents": documents,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if report is not None:
        report_path = REPORT_PATH
        report["generated_at"] = _now_iso()
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)


def merge_documents(
    existing: List[Dict[str, Any]],
    new_docs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge by document_id; new docs replace existing with same id."""
    by_id = {d["document_id"]: d for d in existing}
    for doc in new_docs:
        by_id[doc["document_id"]] = doc
    return list(by_id.values())


def _ingest_entry_list(
    entries: List[ManifestEntry],
    *,
    base_dir: Optional[Path],
    files: Optional[List[str]],
    force: bool,
    dry_run: bool,
    existing_docs: List[Dict[str, Any]],
) -> Tuple[List[IngestResult], List[Dict[str, Any]]]:
    existing_hashes = {
        d["document_id"]: d.get("source_hash") for d in existing_docs
    }
    results: List[IngestResult] = []
    new_documents: List[Dict[str, Any]] = []

    if files:
        file_set = set(files)
        entries = [e for e in entries if e.file in file_set or Path(e.file).name in file_set]

    for entry in entries:
        if not entry.enabled and not files:
            results.append(IngestResult(entry=entry, status="skipped", error="disabled"))
            continue

        file_path = _resolve_file_path(entry, base_dir=base_dir)
        if not file_path.exists():
            results.append(IngestResult(entry=entry, status="skipped", error="file not found"))
            continue

        current_hash = _file_hash(file_path)
        if not force and not dry_run:
            prev_hash = existing_hashes.get(entry.document_id)
            if prev_hash == current_hash:
                results.append(IngestResult(
                    entry=entry, status="skipped",
                    error="unchanged (use --force to re-ingest)",
                    source_hash=current_hash,
                ))
                continue

        result = ingest_manifest_entry(
            entry, dry_run=dry_run, ignore_enabled=bool(files), base_dir=base_dir,
        )
        results.append(result)
        if result.status == "success" and result.document:
            new_documents.append(result.document)

    return results, new_documents


def ingest_all(
    *,
    files: Optional[List[str]] = None,
    force: bool = False,
    dry_run: bool = False,
    include_products: bool = True,
    include_regulations: bool = True,
) -> Tuple[List[IngestResult], Dict[str, Any]]:
    """Ingest manifest entries from product and/or regulation directories."""
    if not include_products and not include_regulations:
        raise ValueError("At least one of include_products / include_regulations must be True")

    existing_data = load_ingested_bundle()
    base_docs = list(existing_data.get("documents", []))
    results: List[IngestResult] = []
    new_documents: List[Dict[str, Any]] = []

    if include_products:
        entries = load_manifest()
        if not entries and not files:
            raise FileNotFoundError(
                f"No manifest at {MANIFEST_PATH}. Run: python scripts/ingest_documents.py --init"
            )
        prod_results, prod_docs = _ingest_entry_list(
            entries, base_dir=None, files=files, force=force, dry_run=dry_run,
            existing_docs=base_docs,
        )
        results.extend(prod_results)
        new_documents.extend(prod_docs)
        base_docs = merge_documents(base_docs, prod_docs)

    if include_regulations:
        reg_entries = load_regulation_manifest()
        reg_results, reg_docs = _ingest_entry_list(
            reg_entries, base_dir=REG_DOCS_ROOT, files=files, force=force,
            dry_run=dry_run, existing_docs=base_docs,
        )
        results.extend(reg_results)
        new_documents.extend(reg_docs)

    report = {
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r.status == "success"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
            "error": sum(1 for r in results if r.status == "error"),
        },
        "results": [
            {
                "file": r.entry.file,
                "document_id": r.entry.document_id,
                "status": r.status,
                "chunk_count": r.chunk_count,
                "page_count": r.page_count,
                "source_hash": r.source_hash,
                "error": r.error,
            }
            for r in results
        ],
    }

    if not dry_run:
        merged = merge_documents(existing_data.get("documents", []), new_documents)
        pruned, pruned_count = _prune_stale_documents(
            merged,
            include_products=include_products,
            include_regulations=include_regulations,
        )
        report["summary"]["pruned"] = pruned_count
        save_ingested_documents(pruned, report=report)

    return results, report


def _active_document_ids(
    *,
    include_products: bool,
    include_regulations: bool,
) -> Set[str]:
    """Document IDs that are still enabled and have files on disk."""
    active: Set[str] = set()
    if include_products:
        for entry in load_manifest():
            if not entry.enabled:
                continue
            if _resolve_file_path(entry).exists():
                active.add(entry.document_id)
    if include_regulations:
        for entry in load_regulation_manifest():
            if not entry.enabled:
                continue
            if _resolve_file_path(entry, base_dir=REG_DOCS_ROOT).exists():
                active.add(entry.document_id)
    return active


def _prune_stale_documents(
    documents: List[Dict[str, Any]],
    *,
    include_products: bool,
    include_regulations: bool,
) -> Tuple[List[Dict[str, Any]], int]:
    """Remove stale docs only within scopes scanned in this ingest run."""
    active_ids = _active_document_ids(
        include_products=include_products,
        include_regulations=include_regulations,
    )
    product_ids = {e.document_id for e in load_manifest()}
    reg_ids = {e.document_id for e in load_regulation_manifest()}

    kept: List[Dict[str, Any]] = []
    pruned_count = 0
    for doc in documents:
        did = doc["document_id"]
        if include_products and did in product_ids and did not in active_ids:
            pruned_count += 1
            continue
        if include_regulations and did in reg_ids and did not in active_ids:
            pruned_count += 1
            continue
        kept.append(doc)
    return kept, pruned_count


def list_ingest_status() -> List[Dict[str, Any]]:
    """Return product + regulation manifest rows with file/ingest status."""
    ingested = {
        d["document_id"]: d
        for d in load_ingested_bundle().get("documents", [])
    }
    rows: List[Dict[str, Any]] = []

    for e in load_manifest():
        file_path = _resolve_file_path(e)
        ingested_doc = ingested.get(e.document_id)
        rows.append({
            "scope": "product",
            "file": e.file,
            "document_id": e.document_id,
            "product_id": e.product_id,
            "enabled": e.enabled,
            "file_exists": file_path.exists(),
            "ingested": ingested_doc is not None,
            "chunk_count": len(ingested_doc.get("chunks", [])) if ingested_doc else 0,
            "source_hash": ingested_doc.get("source_hash") if ingested_doc else None,
        })

    for e in load_regulation_manifest():
        file_path = _resolve_file_path(e, base_dir=REG_DOCS_ROOT)
        ingested_doc = ingested.get(e.document_id)
        rows.append({
            "scope": "regulation",
            "file": e.file,
            "document_id": e.document_id,
            "product_id": e.regulation_id,
            "enabled": e.enabled,
            "file_exists": file_path.exists(),
            "ingested": ingested_doc is not None,
            "chunk_count": len(ingested_doc.get("chunks", [])) if ingested_doc else 0,
            "source_hash": ingested_doc.get("source_hash") if ingested_doc else None,
        })
    return rows


def list_manifest_status() -> List[Dict[str, Any]]:
    """Backward-compatible alias."""
    return list_ingest_status()

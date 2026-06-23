"""
Document Fetcher — 仅从保司官网与监管网站下载公开文件。

允许来源（域名白名单）：
  - 监管：www.gov.cn、*.nfra.gov.cn、*.iachina.cn、*.beijing.gov.cn
  - 保司：catalog.json 中各产品的 source_url 域名

输出：
  - 产品条款 PDF → knowledge_pack/policy_documents/
  - 监管文件正文   → knowledge_pack/regulations/documents/
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpx

from knowledge.ingestion.naming import product_output_filename, regulation_output_filename

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS_CATALOG = ROOT / "knowledge_pack" / "products" / "catalog.json"
REGULATIONS_CATALOG = ROOT / "knowledge_pack" / "regulations" / "catalog.json"
POLICY_DOCS_DIR = ROOT / "knowledge_pack" / "policy_documents"
REG_DOCS_DIR = ROOT / "knowledge_pack" / "regulations" / "documents"
POLICY_MANIFEST = POLICY_DOCS_DIR / "manifest.json"
REG_MANIFEST = ROOT / "knowledge_pack" / "regulations" / "manifest.json"
FETCH_REPORT = ROOT / "knowledge_pack" / "fetch" / "fetch_report.json"

REGULATORY_SUFFIXES = ("nfra.gov.cn", "iachina.cn", "beijing.gov.cn")
REGULATORY_EXACT_HOSTS = frozenset({"www.gov.cn", "gov.cn"})

CLAUSE_LINK_KEYWORDS = (
    "条款", "保险条款", "产品条款", "条款费率", "产品说明书", "费率表",
    "clause", "terms",
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; InsureQueryFetcher/1.0; "
    "+https://github.com/insurance-query; research)"
)

DEFAULT_DELAY_SEC = 1.5
REQUEST_TIMEOUT = 30.0
MAX_REDIRECTS = 5


@dataclass
class FetchResult:
    target_id: str
    target_type: str  # product | regulation
    source_url: str
    status: str  # success | skipped | error
    output_path: str = ""
    content_type: str = ""
    source_hash: str = ""
    bytes_written: int = 0
    message: str = ""
    fetched_at: str = field(default_factory=lambda: _now_iso())


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()[:16]


def _normalize_host(url: str) -> str:
    return urlparse(url).netloc.lower().split(":")[0]


def _host_matches_suffix(host: str, suffix: str) -> bool:
    """Match exact host or proper subdomain (label boundary, not substring)."""
    host = host.lower()
    suffix = suffix.lower().lstrip(".")
    if host == suffix:
        return True
    return host.endswith("." + suffix)


def _is_regulatory_host(host: str) -> bool:
    host = host.lower()
    if host in REGULATORY_EXACT_HOSTS:
        return True
    return any(_host_matches_suffix(host, s) for s in REGULATORY_SUFFIXES)


def build_insurer_domains() -> Set[str]:
    data = _read_json(PRODUCTS_CATALOG)
    domains: Set[str] = set()
    for p in data.get("products", []):
        url = p.get("source_url", "")
        if url:
            domains.add(_normalize_host(url))
    return domains


def is_url_allowed(url: str, insurer_domains: Optional[Set[str]] = None) -> bool:
    """Only insurer catalog domains and regulatory sites."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    host = _normalize_host(url)
    if _is_regulatory_host(host):
        return True
    domains = insurer_domains if insurer_domains is not None else build_insurer_domains()
    if host in domains:
        return True
    for d in domains:
        if host.endswith("." + d) or d.endswith("." + host):
            return True
    return False


def is_host_private(host: str) -> bool:
    """Return True if host resolves to a private/link-local address."""
    host = host.lower().strip()
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        for info in socket.getaddrinfo(host, None):
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
    except (socket.gaierror, ValueError):
        return False
    return False


def validate_fetch_url(url: str, insurer_domains: Optional[Set[str]] = None) -> None:
    """Raise ValueError if URL is not allowed for fetching."""
    host = _normalize_host(url)
    if is_host_private(host):
        raise ValueError(f"URL resolves to private address: {url}")
    if not is_url_allowed(url, insurer_domains):
        raise ValueError(f"URL not in allowlist: {url}")


def is_content_url(url: str) -> bool:
    """Skip bare homepages without document path."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path:
        return False
    # nfra.gov.cn bare root
    if path in ("", "/") and parsed.netloc.count(".") <= 2:
        return False
    return True


def html_to_text(html: str) -> str:
    """Extract readable text from HTML (gov.cn / generic)."""
    for pattern in (
        r"<script[^>]*>.*?</script>",
        r"<style[^>]*>.*?</style>",
        r"<!--.*?-->",
    ):
        html = re.sub(pattern, "", html, flags=re.S | re.I)

    content_match = re.search(
        r'<div[^>]*class="[^"]*pages_content[^"]*"[^>]*>(.*?)</div>',
        html, re.S | re.I,
    )
    if content_match:
        html = content_match.group(1)
    else:
        article_match = re.search(
            r"<article[^>]*>(.*?)</article>", html, re.S | re.I,
        )
        if article_match:
            html = article_match.group(1)

    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"</div>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_links(html: str, base_url: str) -> List[Tuple[str, str]]:
    """Return (absolute_url, link_text) pairs."""
    links: List[Tuple[str, str]] = []
    for m in re.finditer(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html, re.S | re.I,
    ):
        href = m.group(1).strip()
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        abs_url = urljoin(base_url, href)
        links.append((abs_url, text))
    return links


def score_clause_link(url: str, text: str, product_name: str = "") -> int:
    score = 0
    combined = f"{url} {text}"
    lower = combined.lower()
    if url.lower().endswith(".pdf"):
        score += 3
    for kw in CLAUSE_LINK_KEYWORDS:
        if kw in combined or kw in lower:
            score += 2
    if product_name:
        for part in re.split(r"[·\s（(]", product_name):
            part = part.strip()
            if len(part) >= 2 and part in combined:
                score += 2
    return score


class DocumentFetcher:
    def __init__(
        self,
        *,
        delay_sec: float = DEFAULT_DELAY_SEC,
        insurer_domains: Optional[Set[str]] = None,
    ):
        self.delay_sec = delay_sec
        self.insurer_domains = insurer_domains or build_insurer_domains()
        self._last_fetch = 0.0
        self._client = httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "DocumentFetcher":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_fetch
        if elapsed < self.delay_sec:
            time.sleep(self.delay_sec - elapsed)
        self._last_fetch = time.monotonic()

    def fetch_bytes(self, url: str) -> Tuple[bytes, str]:
        validate_fetch_url(url, self.insurer_domains)
        self._throttle()
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            resp = self._client.get(current)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    resp.raise_for_status()
                current = urljoin(current, location)
                validate_fetch_url(current, self.insurer_domains)
                continue
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "application/octet-stream")
            return resp.content, ctype
        raise ValueError(f"Too many redirects for URL: {url}")

    def fetch_html(self, url: str) -> str:
        data, ctype = self.fetch_bytes(url)
        if "pdf" in ctype.lower():
            raise ValueError("URL points to PDF, not HTML")
        for enc in ("utf-8", "gbk", "gb2312"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def find_clause_pdf(
        self, page_url: str, product_name: str, max_depth: int = 1,
    ) -> Optional[str]:
        """BFS on same-domain pages looking for clause PDF links."""
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(page_url, 0)]
        candidates: List[Tuple[int, str]] = []

        while queue:
            url, depth = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            if not is_url_allowed(url, self.insurer_domains):
                continue

            try:
                if url.lower().endswith(".pdf"):
                    score = score_clause_link(url, "", product_name)
                    if score > 0:
                        candidates.append((score, url))
                    continue

                html = self.fetch_html(url)
            except Exception as exc:
                logger.debug("Skip %s: %s", url, exc)
                continue

            for link_url, link_text in extract_links(html, url):
                if link_url.lower().endswith(".pdf"):
                    score = score_clause_link(link_url, link_text, product_name)
                    if score > 0:
                        candidates.append((score, link_url))
                elif depth < max_depth and _normalize_host(link_url) == _normalize_host(page_url):
                    if link_url not in visited:
                        queue.append((link_url, depth + 1))

        if not candidates:
            return None
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    def save_bytes(self, data: bytes, path: Path) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return len(data)

    def _sync_manifest_file(
        self,
        product_id: str,
        actual_path: Path,
        manifest_entry: Optional[Dict[str, Any]],
    ) -> None:
        """Update policy manifest when actual output filename differs."""
        if not POLICY_MANIFEST.exists():
            return
        rel_name = actual_path.name
        manifest = load_policy_manifest()
        updated = False
        for doc in manifest.get("documents", []):
            if doc.get("product_id") == product_id:
                if doc.get("file") != rel_name:
                    doc["file"] = rel_name
                    updated = True
                break
        if updated:
            manifest.setdefault("meta", {})["updated"] = _now_iso()
            _write_json(POLICY_MANIFEST, manifest)

    def fetch_product(
        self,
        product: Dict[str, Any],
        manifest_entry: Optional[Dict[str, Any]] = None,
        *,
        force: bool = False,
    ) -> FetchResult:
        pid = product["product_id"]
        source_url = product.get("source_url", "")
        name = product.get("name", pid)

        if not source_url:
            return FetchResult(pid, "product", "", "skipped", message="no source_url")

        if not is_url_allowed(source_url, self.insurer_domains):
            return FetchResult(pid, "product", source_url, "skipped",
                               message="source_url not in allowlist")

        out_file = (
            manifest_entry.get("file")
            if manifest_entry
            else product_output_filename(product)
        )
        out_path = POLICY_DOCS_DIR / out_file

        if out_path.exists() and not force:
            return FetchResult(
                pid, "product", source_url, "skipped",
                output_path=str(out_path),
                message="file exists (use --force)",
                source_hash=_file_hash(out_path),
            )

        try:
            pdf_url = None
            if manifest_entry and manifest_entry.get("fetch_url"):
                candidate = manifest_entry["fetch_url"]
                try:
                    validate_fetch_url(candidate, self.insurer_domains)
                    pdf_url = candidate
                except ValueError:
                    pass

            if not pdf_url:
                pdf_url = self.find_clause_pdf(source_url, name)

            if pdf_url:
                data, ctype = self.fetch_bytes(pdf_url)
                if not out_file.lower().endswith(".pdf"):
                    out_path = out_path.with_suffix(".pdf")
                nbytes = self.save_bytes(data, out_path)
                self._sync_manifest_file(pid, out_path, manifest_entry)
                return FetchResult(
                    pid, "product", pdf_url, "success",
                    output_path=str(out_path),
                    content_type=ctype,
                    source_hash=_file_hash(out_path),
                    bytes_written=nbytes,
                    message="downloaded PDF",
                )

            # Fallback: save product page text
            html = self.fetch_html(source_url)
            text = html_to_text(html)
            if len(text) < 100:
                return FetchResult(pid, "product", source_url, "error",
                                   message="page too short, no PDF found")

            txt_path = out_path.with_suffix(".txt")
            header = f"# {name}\n来源: {source_url}\n采集时间: {_now_iso()}\n\n"
            txt_path.write_text(header + text, encoding="utf-8")
            self._sync_manifest_file(pid, txt_path, manifest_entry)
            return FetchResult(
                pid, "product", source_url, "success",
                output_path=str(txt_path),
                content_type="text/plain",
                source_hash=_file_hash(txt_path),
                bytes_written=txt_path.stat().st_size,
                message="saved product page text (no PDF found)",
            )
        except Exception as exc:
            logger.exception("Failed to fetch product %s", pid)
            return FetchResult(pid, "product", source_url, "error", message=str(exc))

    def fetch_regulation(
        self, regulation: Dict[str, Any], *, force: bool = False,
    ) -> FetchResult:
        rid = regulation["regulation_id"]
        source_url = regulation.get("source_url", "")
        title = regulation.get("title", rid)

        if not source_url or not is_content_url(source_url):
            return FetchResult(rid, "regulation", source_url or "", "skipped",
                               message="no content URL (homepage placeholder)")

        if not is_url_allowed(source_url, self.insurer_domains):
            return FetchResult(rid, "regulation", source_url, "skipped",
                               message="URL not in regulatory allowlist")

        out_path = REG_DOCS_DIR / regulation_output_filename(regulation, ".txt")

        if out_path.exists() and not force:
            return FetchResult(
                rid, "regulation", source_url, "skipped",
                output_path=str(out_path),
                message="file exists (use --force)",
                source_hash=_file_hash(out_path),
            )

        try:
            data, ctype = self.fetch_bytes(source_url)

            if "pdf" in ctype.lower() or source_url.lower().endswith(".pdf"):
                out_path = out_path.with_suffix(".pdf")
                nbytes = self.save_bytes(data, out_path)
                self._sync_regulation_manifest_file(rid, out_path)
                return FetchResult(
                    rid, "regulation", source_url, "success",
                    output_path=str(out_path),
                    content_type=ctype,
                    source_hash=_file_hash(out_path),
                    bytes_written=nbytes,
                    message="downloaded PDF",
                )

            html = data.decode("utf-8", errors="replace")
            text = html_to_text(html)
            if len(text) < 50:
                return FetchResult(rid, "regulation", source_url, "error",
                                   message="extracted text too short")

            header = (
                f"# {title}\n"
                f"文号: {regulation.get('doc_number', '')}\n"
                f"机关: {regulation.get('agency', '')}\n"
                f"来源: {source_url}\n"
                f"采集时间: {_now_iso()}\n\n"
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(header + text, encoding="utf-8")
            self._sync_regulation_manifest_file(rid, out_path)
            return FetchResult(
                rid, "regulation", source_url, "success",
                output_path=str(out_path),
                content_type="text/plain",
                source_hash=_file_hash(out_path),
                bytes_written=out_path.stat().st_size,
                message="saved regulation text",
            )
        except Exception as exc:
            logger.exception("Failed to fetch regulation %s", rid)
            return FetchResult(rid, "regulation", source_url, "error", message=str(exc))

    def _sync_regulation_manifest_file(self, regulation_id: str, actual_path: Path) -> None:
        if not REG_MANIFEST.exists():
            return
        rel_name = f"documents/{actual_path.name}"
        manifest = _read_json(REG_MANIFEST)
        updated = False
        for doc in manifest.get("documents", []):
            if doc.get("regulation_id") == regulation_id:
                if doc.get("file") != rel_name:
                    doc["file"] = rel_name
                    updated = True
                break
        if updated:
            manifest.setdefault("meta", {})["updated"] = _now_iso()
            _write_json(REG_MANIFEST, manifest)


def load_policy_manifest() -> Dict[str, Any]:
    if not POLICY_MANIFEST.exists():
        return {"documents": []}
    return _read_json(POLICY_MANIFEST)


def init_regulation_manifest() -> Dict[str, Any]:
    """Build regulations/manifest.json from catalog content URLs."""
    catalog = _read_json(REGULATIONS_CATALOG)
    documents = []
    for reg in catalog.get("regulations", []):
        url = reg.get("source_url", "")
        if not is_content_url(url):
            continue
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", reg.get("title", ""))[:40]
        documents.append({
            "file": f"documents/{reg['regulation_id']}_{safe_title}.placeholder",
            "document_id": f"DOC_{reg['regulation_id']}",
            "title": reg.get("title", ""),
            "document_type": "regulation",
            "regulation_id": reg["regulation_id"],
            "source_url": url,
            "enabled": True,
        })
    payload = {
        "meta": {"version": "1.0", "updated": _now_iso(), "total": len(documents)},
        "documents": documents,
    }
    _write_json(REG_MANIFEST, payload)
    return payload


def sync_product_source_urls() -> None:
    """Add source_url from catalog into policy manifest entries."""
    if not POLICY_MANIFEST.exists():
        return
    catalog = {p["product_id"]: p for p in _read_json(PRODUCTS_CATALOG).get("products", [])}
    manifest = load_policy_manifest()
    for doc in manifest.get("documents", []):
        pid = doc.get("product_id")
        if pid and pid in catalog:
            doc["source_url"] = catalog[pid].get("source_url", "")
    manifest.setdefault("meta", {})["updated"] = _now_iso()
    _write_json(POLICY_MANIFEST, manifest)


def fetch_products(
    *,
    product_ids: Optional[List[str]] = None,
    force: bool = False,
    delay_sec: float = DEFAULT_DELAY_SEC,
) -> Tuple[List[FetchResult], Dict[str, Any]]:
    sync_product_source_urls()
    catalog = _read_json(PRODUCTS_CATALOG).get("products", [])
    manifest_by_pid = {
        d["product_id"]: d
        for d in load_policy_manifest().get("documents", [])
        if d.get("product_id")
    }

    if product_ids:
        catalog = [p for p in catalog if p["product_id"] in product_ids]

    results: List[FetchResult] = []
    with DocumentFetcher(delay_sec=delay_sec) as fetcher:
        for product in catalog:
            entry = manifest_by_pid.get(product["product_id"])
            results.append(fetcher.fetch_product(product, entry, force=force))

    report = _build_report(results)
    _write_json(FETCH_REPORT, report)
    return results, report


def fetch_regulations(
    *,
    regulation_ids: Optional[List[str]] = None,
    force: bool = False,
    delay_sec: float = DEFAULT_DELAY_SEC,
) -> Tuple[List[FetchResult], Dict[str, Any]]:
    init_regulation_manifest()
    catalog = _read_json(REGULATIONS_CATALOG).get("regulations", [])
    if regulation_ids:
        catalog = [r for r in catalog if r["regulation_id"] in regulation_ids]

    results: List[FetchResult] = []
    with DocumentFetcher(delay_sec=delay_sec) as fetcher:
        for reg in catalog:
            results.append(fetcher.fetch_regulation(reg, force=force))

    report = _build_report(results)
    _write_json(FETCH_REPORT, report)
    return results, report


def _build_report(results: List[FetchResult]) -> Dict[str, Any]:
    return {
        "generated_at": _now_iso(),
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r.status == "success"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
            "error": sum(1 for r in results if r.status == "error"),
        },
        "allowed_insurer_domains": sorted(build_insurer_domains()),
        "results": [
            {
                "target_id": r.target_id,
                "target_type": r.target_type,
                "source_url": r.source_url,
                "status": r.status,
                "output_path": r.output_path,
                "message": r.message,
                "bytes_written": r.bytes_written,
                "source_hash": r.source_hash,
            }
            for r in results
        ],
    }


def list_fetch_targets() -> Dict[str, Any]:
    products = _read_json(PRODUCTS_CATALOG).get("products", [])
    regulations = _read_json(REGULATIONS_CATALOG).get("regulations", [])
    reg_fetchable = [r for r in regulations if is_content_url(r.get("source_url", ""))]
    return {
        "insurer_domains": sorted(build_insurer_domains()),
        "products": len(products),
        "regulations_total": len(regulations),
        "regulations_fetchable": len(reg_fetchable),
        "regulations_skipped_homepage": len(regulations) - len(reg_fetchable),
    }

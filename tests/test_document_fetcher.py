"""Tests for document fetcher (insurer + regulatory allowlist)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from knowledge.ingestion.document_fetcher import (
    DocumentFetcher,
    build_insurer_domains,
    html_to_text,
    init_regulation_manifest,
    is_content_url,
    is_url_allowed,
    score_clause_link,
)

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_CATALOG = {
    "products": [
        {"product_id": "P001", "name": "测试", "source_url": "https://health.pingan.com"},
    ]
}


class TestAllowlist:
    def test_insurer_domains_from_catalog(self, monkeypatch, tmp_path):
        import knowledge.ingestion.document_fetcher as df

        cat = tmp_path / "catalog.json"
        cat.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")
        monkeypatch.setattr(df, "PRODUCTS_CATALOG", cat)
        domains = build_insurer_domains()
        assert "health.pingan.com" in domains

    def test_regulatory_urls_allowed(self):
        assert is_url_allowed("https://www.gov.cn/zhengce/foo.htm")
        assert is_url_allowed("https://www.nfra.gov.cn/cn/view/pages/xxx.html")
        assert is_url_allowed("http://www.iachina.cn/art/2020/11/5/art_22_104708.html")

    def test_random_domain_blocked(self):
        assert not is_url_allowed("https://www.zhihu.com/question/123")
        assert not is_url_allowed("https://www.huize.com/products")

    def test_insurer_catalog_domain_allowed(self, monkeypatch, tmp_path):
        import knowledge.ingestion.document_fetcher as df

        cat = tmp_path / "catalog.json"
        cat.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")
        monkeypatch.setattr(df, "PRODUCTS_CATALOG", cat)
        assert is_url_allowed("https://health.pingan.com/products")

    def test_homepage_placeholder_skipped(self):
        assert not is_content_url("https://www.nfra.gov.cn")
        assert is_content_url("https://www.gov.cn/zhengce/zhengceku/2019-12/04/content_5458542.htm")


class TestHtmlParsing:
    def test_html_to_text_strips_tags(self):
        html = "<html><body><p>第一条 等待期30日</p><p>第二条 免赔额1万</p></body></html>"
        text = html_to_text(html)
        assert "等待期" in text
        assert "<p>" not in text

    def test_score_clause_pdf_link(self):
        assert score_clause_link("https://x.com/clause.pdf", "产品条款") > 0
        assert score_clause_link("https://x.com/about.html", "关于我们") == 0


class TestFetcherMocked:
    SAMPLE_GOV_HTML = """
    <html><body><div class="pages_content">
    <p>第一条 为规范健康保险经营，制定本办法。</p>
    <p>第二条 本办法所称健康保险，是指保险公司对被保险人因健康原因所致损失给付保险金的保险。</p>
    </div></body></html>
    """

    def test_fetch_regulation_saves_text(self, tmp_path, monkeypatch):
        import knowledge.ingestion.document_fetcher as df

        reg_dir = tmp_path / "regulations" / "documents"
        monkeypatch.setattr(df, "REG_DOCS_DIR", reg_dir)

        fetcher = DocumentFetcher(insurer_domains={"health.pingan.com"})
        fetcher.fetch_bytes = MagicMock(return_value=(self.SAMPLE_GOV_HTML.encode(), "text/html"))

        reg = {
            "regulation_id": "REG_TEST",
            "title": "测试办法",
            "agency": "测试机关",
            "source_url": "https://www.gov.cn/zhengce/test.htm",
        }
        result = fetcher.fetch_regulation(reg, force=True)
        assert result.status == "success"
        assert Path(result.output_path).exists()
        assert "第一条" in Path(result.output_path).read_text(encoding="utf-8")
        fetcher.close()

    def test_fetch_product_blocked_domain(self):
        fetcher = DocumentFetcher()
        product = {
            "product_id": "PX",
            "name": "测试",
            "source_url": "https://evil.example.com",
        }
        result = fetcher.fetch_product(product, force=True)
        assert result.status == "skipped"
        assert "allowlist" in result.message
        fetcher.close()


class TestRegulationManifest:
    def test_init_regulation_manifest(self, tmp_path, monkeypatch):
        import knowledge.ingestion.document_fetcher as df

        reg_cat = tmp_path / "reg_catalog.json"
        reg_cat.write_text(json.dumps({
            "regulations": [{
                "regulation_id": "REG001",
                "title": "测试法规",
                "source_url": "https://www.gov.cn/zhengce/test.htm",
            }]
        }), encoding="utf-8")
        monkeypatch.setattr(df, "REGULATIONS_CATALOG", reg_cat)
        monkeypatch.setattr(df, "REG_MANIFEST", tmp_path / "manifest.json")
        data = init_regulation_manifest()
        assert data["meta"]["total"] == 1

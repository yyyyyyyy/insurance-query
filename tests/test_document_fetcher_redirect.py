"""Document fetcher redirect SSRF protection tests."""

import pytest

from knowledge.ingestion.document_fetcher import (
    is_url_allowed,
    validate_fetch_url,
    is_host_private,
)


class TestRedirectSecurity:
    def test_private_host_blocked(self):
        assert is_host_private("localhost") is True
        assert is_host_private("127.0.0.1") is True

    def test_validate_rejects_private_url(self):
        with pytest.raises(ValueError, match="private"):
            validate_fetch_url("http://127.0.0.1/secret")

    def test_evil_subdomain_not_regulatory(self):
        assert is_url_allowed("https://evilnfra.gov.cn/x") is False

    def test_nfra_suffix_allowed(self):
        assert is_url_allowed("https://www.nfra.gov.cn/x") is True

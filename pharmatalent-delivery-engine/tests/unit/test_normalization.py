"""Unit tests for normalization utilities."""
import pytest
from app.domain.normalization import (
    normalize_company_name,
    normalize_full_name,
    canonicalize_linkedin_url,
    extract_domain_from_url,
    root_domain,
    parse_size_band,
)


class TestNormalizeCompanyName:
    def test_strips_gmbh(self):
        assert normalize_company_name("Evotec GmbH") == "evotec"

    def test_strips_ag(self):
        assert normalize_company_name("Molecular Partners AG") == "molecular partners"

    def test_strips_plc(self):
        assert normalize_company_name("ICON plc") == "icon"

    def test_strips_parenthetical_country(self):
        assert normalize_company_name("Roche (Switzerland)") == "roche"

    def test_lowercases(self):
        assert normalize_company_name("AstraZeneca") == "astrazeneca"

    def test_strips_gmbh_co_kg(self):
        result = normalize_company_name("Boehringer Ingelheim GmbH & Co. KG")
        assert "boehringer ingelheim" in result
        assert "gmbh" not in result

    def test_collapses_whitespace(self):
        result = normalize_company_name("  Pfizer   Inc.  ")
        assert result == "pfizer"

    def test_empty_string(self):
        assert normalize_company_name("") == ""

    def test_strips_se(self):
        assert normalize_company_name("BioNTech SE") == "biontech"


class TestNormalizeFullName:
    def test_lowercase_accent_strip(self):
        assert normalize_full_name("Anna Müller") == "anna muller"

    def test_collapses_spaces(self):
        assert normalize_full_name("  John   Doe  ") == "john doe"


class TestCanonicalizeLinkedInUrl:
    def test_strips_query_params(self):
        url = "https://www.linkedin.com/in/janedoe/?originalSubdomain=de"
        assert canonicalize_linkedin_url(url) == "https://www.linkedin.com/in/janedoe"

    def test_strips_trailing_slash(self):
        url = "https://linkedin.com/in/john-doe/"
        assert canonicalize_linkedin_url(url) == "https://www.linkedin.com/in/john-doe"

    def test_empty_string(self):
        assert canonicalize_linkedin_url("") == ""


class TestExtractDomain:
    def test_strips_www(self):
        assert extract_domain_from_url("https://www.biontech.de/en") == "biontech.de"

    def test_handles_no_scheme(self):
        result = extract_domain_from_url("evotec.com")
        assert "evotec" in result

    def test_empty(self):
        assert extract_domain_from_url("") == ""


class TestRootDomain:
    def test_extracts_root(self):
        assert root_domain("biontech.de") == "biontech"

    def test_handles_subdomain(self):
        assert root_domain("careers.novartis.com") == "novartis"


class TestParseSizeBand:
    def test_small_band(self):
        assert parse_size_band(100, None) == "50-200"

    def test_mid_band(self):
        assert parse_size_band(500, None) == "201-1000"

    def test_large_band(self):
        assert parse_size_band(1500, None) == "1001-2000"

    def test_out_of_range(self):
        assert parse_size_band(50000, None) is None

    def test_from_text(self):
        assert parse_size_band(None, "51-200 employees") == "50-200"

    def test_from_text_mid(self):
        assert parse_size_band(None, "201-500 employees") == "201-1000"

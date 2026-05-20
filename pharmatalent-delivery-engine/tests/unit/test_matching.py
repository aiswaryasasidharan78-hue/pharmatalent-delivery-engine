"""Unit tests for active-client exclusion matching."""
import pytest
from app.domain.matching import check_active_client


class TestCheckActiveClient:
    def test_exact_match(self):
        result = check_active_client("Pfizer")
        assert result.is_excluded is True
        assert result.match_method == "exact"

    def test_exact_match_with_suffix(self):
        result = check_active_client("Pfizer Inc.")
        assert result.is_excluded is True

    def test_exact_match_biontech_se(self):
        result = check_active_client("BioNTech SE")
        assert result.is_excluded is True

    def test_fuzzy_match_typo(self):
        result = check_active_client("Pfizerr")
        assert result.is_excluded is True
        assert result.match_method == "fuzzy"

    def test_domain_match(self):
        result = check_active_client("Unknown Name", company_domain="biontech.de")
        assert result.is_excluded is True
        assert result.match_method == "domain"

    def test_gsk_abbreviation(self):
        result = check_active_client("GSK")
        assert result.is_excluded is True

    def test_glaxosmithkline_full_name(self):
        result = check_active_client("GlaxoSmithKline")
        assert result.is_excluded is True

    def test_unknown_company_not_excluded(self):
        result = check_active_client("Molecular Partners AG")
        assert result.is_excluded is False

    def test_empty_name(self):
        result = check_active_client("")
        assert result.is_excluded is False

    def test_roche_with_country_tag(self):
        result = check_active_client("Roche (Switzerland)")
        assert result.is_excluded is True

    def test_astrazeneca_case_insensitive(self):
        result = check_active_client("astrazeneca")
        assert result.is_excluded is True

    def test_merck_kgaa(self):
        result = check_active_client("Merck KGaA")
        assert result.is_excluded is True

    def test_icon_plc(self):
        result = check_active_client("ICON plc")
        assert result.is_excluded is True

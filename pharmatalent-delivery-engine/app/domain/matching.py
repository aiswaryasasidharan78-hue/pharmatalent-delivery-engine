"""
Active-client matching.

Matching strategy (applied in order, stop on first hit):
  1. Exact match on normalized name
  2. Domain match on root domain
  3. Fuzzy match — Levenshtein ≤ 2 OR similarity ≥ 90%
"""
from __future__ import annotations

from typing import Optional

from rapidfuzz import fuzz, distance

from app.domain.normalization import normalize_company_name, root_domain
from app.domain.schemas import ExclusionResult

# ─── Active-client list (from ACTIVE_CLIENTS.md) ─────────────────────────────
ACTIVE_CLIENT_NAMES: list[str] = [
    # Big pharma
    "Pfizer",
    "Bayer",
    "Novartis",
    "Roche",
    "Sanofi",
    "GSK",
    "GlaxoSmithKline",
    "AstraZeneca",
    "Merck KGaA",
    "Boehringer Ingelheim",
    # Mid biotech
    "BioNTech",
    "CureVac",
    "MorphoSys",
    "Evotec",
    # CROs
    "ICON plc",
    "IQVIA",
]

# Pre-normalize the list once at import time
_NORMALIZED_CLIENTS: list[tuple[str, str]] = [
    (normalize_company_name(c), c) for c in ACTIVE_CLIENT_NAMES
]

# Known domains for active clients (root domain → canonical name)
_CLIENT_DOMAINS: dict[str, str] = {
    "pfizer": "Pfizer",
    "bayer": "Bayer",
    "novartis": "Novartis",
    "roche": "Roche",
    "sanofi": "Sanofi",
    "gsk": "GSK",
    "glaxosmithkline": "GlaxoSmithKline",
    "astrazeneca": "AstraZeneca",
    "merck": "Merck KGaA",
    "boehringer-ingelheim": "Boehringer Ingelheim",
    "biontech": "BioNTech",
    "curevac": "CureVac",
    "morphosys": "MorphoSys",
    "evotec": "Evotec",
    "iconplc": "ICON plc",
    "iqvia": "IQVIA",
}

_FUZZY_SIMILARITY_THRESHOLD = 90
_LEVENSHTEIN_THRESHOLD = 2


def check_active_client(
    company_name: str,
    company_domain: Optional[str] = None,
) -> ExclusionResult:
    """
    Returns ExclusionResult.is_excluded=True if the company is on the
    active-client list.  Logs the match method for auditability.
    """
    norm = normalize_company_name(company_name)

    # 1. Exact match
    for client_norm, client_raw in _NORMALIZED_CLIENTS:
        if norm == client_norm:
            return ExclusionResult(
                is_excluded=True,
                matched_client=client_raw,
                match_method="exact",
                raw_company_name=company_name,
            )

    # 2. Domain match
    if company_domain:
        rd = root_domain(company_domain.lower())
        if rd in _CLIENT_DOMAINS:
            return ExclusionResult(
                is_excluded=True,
                matched_client=_CLIENT_DOMAINS[rd],
                match_method="domain",
                raw_company_name=company_name,
            )

    # 3. Fuzzy match
    for client_norm, client_raw in _NORMALIZED_CLIENTS:
        lev = distance.Levenshtein.distance(norm, client_norm)
        sim = fuzz.ratio(norm, client_norm)
        if lev <= _LEVENSHTEIN_THRESHOLD or sim >= _FUZZY_SIMILARITY_THRESHOLD:
            return ExclusionResult(
                is_excluded=True,
                matched_client=client_raw,
                match_method="fuzzy",
                raw_company_name=company_name,
            )

    return ExclusionResult(is_excluded=False, raw_company_name=company_name)

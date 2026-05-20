"""
Normalization utilities.

Company name normalization is critical for:
  1. Active-client exclusion matching
  2. Deduplication of companies across multiple job postings
  3. DMM cache key generation

LinkedIn URL canonicalization is used for contact dedup.
"""
from __future__ import annotations

import re
import urllib.parse
from unicodedata import normalize as unicode_normalize

from unidecode import unidecode

# Legal suffixes to strip (order matters — strip longer ones first)
_LEGAL_SUFFIXES = [
    r"\bGmbH\s*&\s*Co\.\s*KG\b",
    r"\bGmbH\b",
    r"\bAktiengesellschaft\b",
    r"\bAG\b",
    r"\bSE\b",
    r"\bS\.A\.S\.\b",
    r"\bS\.A\.\b",
    r"\bS\.p\.A\.\b",
    r"\bInc\.\b",
    r"\bInc\b",
    r"\bLtd\.\b",
    r"\bLtd\b",
    r"\bLLC\b",
    r"\bplc\b",
    r"\bHolding\b",
    r"\bB\.V\.\b",
    r"\bN\.V\.\b",
    r"\bOy\b",
    r"\bAB\b",
    r"\bASA\b",
]

_LEGAL_RE = re.compile(
    r"(?i)(?:" + "|".join(_LEGAL_SUFFIXES) + r")",
)

# Country/region tags in parentheses or after comma
_PAREN_TAG_RE = re.compile(r"\s*\(.*?\)\s*")
_COMMA_TAG_RE = re.compile(r",.*$")


def normalize_company_name(name: str) -> str:
    """
    Returns a lowercase, accent-stripped, whitespace-collapsed company name
    suitable for matching against the active-client list.

    Steps:
      1. Transliterate accents (Björn → Bjorn)
      2. Strip parenthetical country tags
      3. Strip trailing comma tags
      4. Remove legal suffixes
      5. Lowercase + collapse whitespace
    """
    if not name:
        return ""
    s = unidecode(name)  # accent strip
    s = _PAREN_TAG_RE.sub(" ", s)
    s = _COMMA_TAG_RE.sub("", s)
    s = _LEGAL_RE.sub(" ", s)
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)  # punctuation → space
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_full_name(name: str) -> str:
    """Lowercase, accent-strip, single-space — used as contact dedup key."""
    if not name:
        return ""
    s = unidecode(name).lower()
    return re.sub(r"\s+", " ", s).strip()


def canonicalize_linkedin_url(url: str) -> str:
    """
    Strip query params, trailing slash, and language prefix from a LinkedIn URL.

    Examples:
      https://www.linkedin.com/in/janedoe/?originalSubdomain=de
        → https://www.linkedin.com/in/janedoe
      https://linkedin.com/in/john-doe/
        → https://www.linkedin.com/in/john-doe
    """
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    # Strip language prefix like /in/en-gb/...
    path = re.sub(r"^(/in)/[a-z]{2}-[a-z]{2}/", r"\1/", path)
    canonical = f"https://www.linkedin.com{path}"
    return canonical


def extract_domain_from_url(url: str) -> str:
    """
    Extract root domain from a URL.
    https://www.biontech.de/en → biontech.de
    """
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
        host = parsed.netloc or parsed.path
        host = re.sub(r"^www\.", "", host).lower()
        host = host.split(":")[0]  # strip port
        return host
    except Exception:
        return ""


def root_domain(domain: str) -> str:
    """biontech.de → biontech"""
    if not domain:
        return ""
    parts = domain.split(".")
    return parts[-2] if len(parts) >= 2 else parts[0]


def parse_size_band(
    employee_count: int | None,
    size_text: str | None,
) -> str | None:
    """Map employee count (or LinkedIn size-band text) to our 3-band schema."""
    if employee_count is not None:
        if 50 <= employee_count <= 200:
            return "50-200"
        elif 201 <= employee_count <= 1000:
            return "201-1000"
        elif 1001 <= employee_count <= 2000:
            return "1001-2000"
        return None  # outside target band

    if size_text:
        text = size_text.lower()
        # LinkedIn size strings like "51-200 employees", "201-500 employees"
        match = re.search(r"(\d+)[\s\-–]+(\d+)", text)
        if match:
            lo, hi = int(match.group(1)), int(match.group(2))
            mid = (lo + hi) // 2
            if mid <= 200:
                return "50-200"
            elif mid <= 1000:
                return "201-1000"
            elif mid <= 2000:
                return "1001-2000"
    return None

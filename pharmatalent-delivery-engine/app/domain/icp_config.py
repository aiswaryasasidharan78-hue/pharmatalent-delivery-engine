"""
ICP configuration constants.  Single source of truth for scrape parameters
and fit-check criteria — mirrors ICP.md exactly.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Half 1 — Apify scrape parameters
# ─────────────────────────────────────────────────────────────────────────────

TITLE_SEARCHES: list[str] = [
    # Regulatory Affairs
    "Regulatory Affairs Manager",
    "Senior Regulatory Affairs Manager",
    "Director Regulatory Affairs",
    "Head of Regulatory Affairs",
    "Regulatory Affairs Specialist",
    # Clinical Operations & Research
    "Clinical Operations Manager",
    "Director Clinical Operations",
    "Head of Clinical Operations",
    "Senior Clinical Research Associate",
    "Clinical Trial Manager",
    "Clinical Project Manager",
    # Pharmacovigilance & Drug Safety
    "Pharmacovigilance Manager",
    "Drug Safety Officer",
    "Qualified Person for Pharmacovigilance",
    # Medical Affairs
    "Medical Affairs Lead",
    "Medical Science Liaison",
    "Senior Medical Advisor",
]

LOCATION_SEARCHES: list[str] = [
    "Germany",
    "Switzerland",
    "Netherlands",
    "Belgium",
    "Denmark",
    "Sweden",
    "Ireland",
    "France",
    "United Kingdom",
    "Spain",
    "Italy",
    "Austria",
    "Finland",
    "Norway",
]

EMPLOYMENT_TYPE_FILTERS: list[str] = ["FULL_TIME", "CONTRACTOR"]

# ─────────────────────────────────────────────────────────────────────────────
# Half 2 — Company fit-check criteria
# ─────────────────────────────────────────────────────────────────────────────

TARGET_INDUSTRIES: list[str] = [
    "biotech",
    "pharmaceutical",
    "pharma",
    "drug discovery",
    "drug development",
    "gene therapy",
    "cell therapy",
    "mRNA",
    "immunotherapy",
    "oncology",
    "rare disease",
    "clinical stage",
    "CRO",
    "contract research",
    "CDMO",
    "contract development",
]

MIN_EMPLOYEES = 50
MAX_EMPLOYEES = 2000

EU_COUNTRIES: set[str] = {
    "Germany", "Switzerland", "Netherlands", "Belgium", "Denmark",
    "Sweden", "Ireland", "France", "United Kingdom", "Spain", "Italy",
    "Austria", "Finland", "Norway", "Poland", "Portugal", "Czech Republic",
    "Hungary", "Romania", "Slovakia", "Slovenia", "Estonia", "Latvia",
    "Lithuania", "Luxembourg", "Malta", "Cyprus", "Bulgaria", "Croatia",
    "Greece", "Iceland", "Liechtenstein",
}

DISQUALIFIERS: list[str] = [
    "university",
    "academic institution",
    "research institute",
    "hospital",
    "clinic",
    "generic drug manufacturer",
    "fully remote",
    "staffing agency",
    "recruitment agency",
    "consulting agency",
    "medical device",
    "cosmetic",
    "nutraceutical",
    "food supplement",
]

# ─────────────────────────────────────────────────────────────────────────────
# DMM — Title bands per company size
# ─────────────────────────────────────────────────────────────────────────────

DMM_TITLE_BANDS: dict[str, list[str]] = {
    "50-200": [
        "Head of Talent",
        "Head of People",
        "Head of HR",
        "Director Regulatory Affairs",
        "Director Clinical Operations",
    ],
    "201-1000": [
        "VP People",
        "VP Talent Acquisition",
        "Senior Director Regulatory Affairs",
        "Senior Director Clinical Operations",
        "Director Talent Acquisition Europe",
    ],
    "1001-2000": [
        "Global Head of Talent",
        "EU Head of Talent Acquisition",
        "VP Regulatory Affairs EU",
        "VP Clinical Operations EU",
        "Senior Director Talent Acquisition",
    ],
}

EU_REGIONS: dict[str, list[str]] = {
    "DACH": ["Germany", "Austria", "Switzerland"],
    "Benelux": ["Netherlands", "Belgium", "Luxembourg"],
    "Nordics": ["Denmark", "Sweden", "Finland", "Norway", "Iceland"],
    "UKI": ["United Kingdom", "Ireland"],
    "Southern Europe": ["France", "Spain", "Italy", "Portugal", "Greece"],
}

"""
PharmaTalent Europe — Lead Discovery Pipeline
Entry point: python -m app.main  OR  python app/main.py
"""
from __future__ import annotations

import sys

from app.pipeline.orchestrator import run_pipeline


def main() -> None:
    summary = run_pipeline()
    if summary.errors:
        print(f"\n⚠️  Pipeline completed with {len(summary.errors)} error(s):")
        for err in summary.errors:
            print(f"  • {err}")
        sys.exit(1)
    else:
        print(
            f"\n✅ Pipeline completed successfully.\n"
            f"   Jobs scraped:        {summary.jobs_scraped}\n"
            f"   Companies ICP fit:   {summary.companies_icp_fit}\n"
            f"   Contacts validated:  {summary.contacts_validated}\n"
            f"   Contacts dropped:    {summary.contacts_dropped}\n"
            f"   DMM cache hits:      {summary.dmm_cache_hits}\n"
            f"   Run ID:              {summary.run_id}\n"
        )


if __name__ == "__main__":
    main()

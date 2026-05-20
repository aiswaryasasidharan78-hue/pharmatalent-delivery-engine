"""
Supabase client singleton.

All database access is routed through this module — no raw Supabase
calls outside the db/ package.  This keeps the persistence boundary clean
and makes it trivial to mock in tests.
"""
from __future__ import annotations

from supabase import create_client, Client

from app.core.config import get_settings

_client: Client | None = None


def get_supabase_client() -> Client:
    global _client
    if _client is None:
        cfg = get_settings()
        _client = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
    return _client

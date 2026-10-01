"""Supabase client setup.

Exposes a single, reusable Supabase client for the whole app. The client is
created lazily on first use so that importing this module never fails at
startup — a missing credential surfaces as a clear error instead.

Authenticates with the service_role key: this process runs server-side, so the
key stays private, and RLS is bypassed rather than silently filtering results.
"""

from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return the shared Supabase client, creating it on first call."""
    settings.validate()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)

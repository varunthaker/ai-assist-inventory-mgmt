"""Health check route.

GET /health reports whether the API is up and whether it can reach Supabase.
The connectivity probe is the equivalent of SELECT count(*) FROM products.
"""

from fastapi import APIRouter, Response, status

from app.db import get_supabase

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response) -> dict:
    """Return API status plus a live Supabase connectivity check."""
    try:
        client = get_supabase()
        # head=True asks for the count only, no rows transferred.
        result = client.table("products").select("*", count="exact", head=True).execute()
        return {
            "status": "ok",
            "database": "connected",
            "products_count": result.count,
        }
    except Exception as exc:  # noqa: BLE001 - surface any failure to the caller
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "degraded",
            "database": "unreachable",
            "error": f"{type(exc).__name__}: {exc}",
        }

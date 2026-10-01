"""Application configuration.

Loads environment variables from a local .env file (if present) and exposes
them as a simple settings object. Nothing is hardcoded — copy .env.example to
.env and fill in your Supabase credentials.

Key names mirror what the Supabase dashboard calls them:
  service_role -> SUPABASE_SERVICE_ROLE_KEY  (secret, bypasses RLS, backend)
  anon         -> SUPABASE_ANON_KEY          (public, respects RLS, frontend)
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# <repo root>/.env  (this file lives at <repo root>/app/config.py)
PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    # The backend authenticates as service_role: it runs server-side, so the
    # key is never exposed, and bypassing RLS means queries are not silently
    # filtered to zero rows before any access policies exist.
    supabase_service_role_key: str
    # Public key, unused by the backend (the React frontend, in its own repo,
    # would use this kind of key). Optional.
    supabase_anon_key: str = ""

    # LLM used by the agent.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # Empty means OpenAI. Set it to use any OpenAI-compatible provider
    # (Groq, Ollama, ...) without code changes.
    openai_base_url: str = ""
    # "low" / "medium" / "high" for reasoning models (gpt-oss, o-series); empty
    # to not send it -- non-reasoning models like gpt-4o-mini reject it.
    openai_reasoning_effort: str = ""

    # Embedding model for RAG (PDF chunks and search queries). Separate from the
    # chat LLM above because Groq has no embeddings endpoint. The dimension must
    # match vector(N) in sql/sop_documents.sql.
    embedding_api_key: str = ""
    # Explicit default on purpose: the OpenAI client falls back to the
    # OPENAI_BASE_URL env var when given none, which points at Groq for the
    # chat model -- embeddings would silently go to Groq and fail with 401.
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Browser origins allowed to call this API (the React dev server). Without
    # CORS the browser blocks a page on another port from reading responses.
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    # Where the agent connects to the MCP server. It is mounted in this same
    # app, so this is our own /mcp; point it elsewhere to use a remote server.
    mcp_server_url: str = "http://127.0.0.1:8000/mcp"
    # Extra hostnames allowed to reach /mcp, e.g. an ngrok domain. Localhost is
    # always allowed; any other Host header gets 421 (DNS-rebinding protection).
    mcp_allowed_hosts: tuple[str, ...] = ()

    def validate(self) -> None:
        """Raise a clear error if required credentials are missing."""
        missing = [
            name
            for name, value in (
                ("SUPABASE_URL", self.supabase_url),
                ("SUPABASE_SERVICE_ROLE_KEY", self.supabase_service_role_key),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                f"Missing required environment variable(s): {', '.join(missing)}. "
                f"Copy .env.example to .env in {PROJECT_DIR} and fill them in."
            )

    def validate_embeddings(self) -> None:
        """Raise a clear error if the embedding model's key is missing."""
        if not self.embedding_api_key:
            raise RuntimeError(
                "Missing required environment variable: EMBEDDING_API_KEY "
                "(an OpenAI key, platform.openai.com/api-keys). "
                f"Add it to {PROJECT_DIR / '.env'} to upload or search documents."
            )

    def validate_openai(self) -> None:
        """Raise a clear error if the agent's LLM credentials are missing.

        Checked separately from Supabase so /health works without an LLM key.
        """
        if not self.openai_api_key:
            raise RuntimeError(
                "Missing required environment variable: OPENAI_API_KEY. "
                f"Add it to {PROJECT_DIR / '.env'} to use POST /chat."
            )


settings = Settings(
    supabase_url=os.getenv("SUPABASE_URL", ""),
    supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
    supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
    openai_api_key=os.getenv("OPENAI_API_KEY", ""),
    openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    openai_base_url=os.getenv("OPENAI_BASE_URL", ""),
    openai_reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", ""),
    embedding_api_key=os.getenv("EMBEDDING_API_KEY", ""),
    embedding_base_url=os.getenv("EMBEDDING_BASE_URL") or "https://api.openai.com/v1",
    embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
    embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "1536")),
    cors_origins=tuple(
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if o.strip()
    ),
    mcp_server_url=os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"),
    mcp_allowed_hosts=tuple(
        h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()
    ),
)

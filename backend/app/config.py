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

# backend/.env  (this file lives at backend/app/config.py)
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    # The backend authenticates as service_role: it runs server-side, so the
    # key is never exposed, and bypassing RLS means queries are not silently
    # filtered to zero rows before any access policies exist.
    supabase_service_role_key: str
    # Public key, unused by the backend. Kept here so the React frontend has
    # one place to read it from later.
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
                f"Copy .env.example to .env in {BACKEND_DIR} and fill them in."
            )

    def validate_openai(self) -> None:
        """Raise a clear error if the agent's LLM credentials are missing.

        Checked separately from Supabase so /health works without an LLM key.
        """
        if not self.openai_api_key:
            raise RuntimeError(
                "Missing required environment variable: OPENAI_API_KEY. "
                f"Add it to {BACKEND_DIR / '.env'} to use POST /chat."
            )


settings = Settings(
    supabase_url=os.getenv("SUPABASE_URL", ""),
    supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
    supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
    openai_api_key=os.getenv("OPENAI_API_KEY", ""),
    openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    openai_base_url=os.getenv("OPENAI_BASE_URL", ""),
    openai_reasoning_effort=os.getenv("OPENAI_REASONING_EFFORT", ""),
    mcp_server_url=os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"),
    mcp_allowed_hosts=tuple(
        h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()
    ),
)

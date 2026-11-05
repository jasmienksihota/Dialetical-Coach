"""Settings, .env loading and the fixed topic-tag catalog.

Secrets are read from environment variables only and are never serialized to the
browser (see ``Settings.public_dict``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The seven overlapping topic categories (shared with the NotebookLM catalog).
TAGS: list[tuple[str, str]] = [
    ("organization", "Building the organization"),
    ("cadre", "Cadre development"),
    ("mass", "Mass consciousness and mass work"),
    ("strategy", "Strategy, tactics and alliances"),
    ("national-liberation", "National liberation and colonialism"),
    ("investigation", "Investigation, learning and correcting mistakes"),
    ("foundations", "Foundations and historical records"),
]
TAG_SLUGS = {slug for slug, _ in TAGS}

DEMO_LABEL = "Demo: scripted responses, not live tutoring."


def load_dotenv(path: Path, environ=None) -> None:
    """Minimal .env loader. Empty values are ignored so placeholders never count."""
    environ = os.environ if environ is None else environ
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and key not in environ:
            environ[key] = value


TOKENS_CEILING = 4096   # hard upper bound on output tokens per request, whatever .env says


def _int(environ, key, default, lo, hi):
    try:
        v = int(float(environ.get(key) or default))
    except ValueError:
        v = default
    return max(lo, min(hi, v))


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000
    max_upload_bytes: int = 25 * 1024 * 1024
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    anthropic_max_tokens: int = 2048
    force_no_fts: bool = False
    # --- bounded live-test controls (all enforced server-side) ---
    live_enabled: bool = False             # TUTOR_LIVE_ENABLED=1 must be set explicitly
    live_max_requests_per_day: int = 20    # API requests per UTC day, persisted in SQLite
    live_max_retries: int = 1              # extra attempts after a transient failure (0-2)
    live_max_input_chars: int = 48000      # refuse to send larger prompts (rough size guard)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tutor.db"

    @property
    def originals_dir(self) -> Path:
        return self.data_dir / "originals"

    @property
    def live_configured(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_model and self.live_enabled)

    @property
    def live_setup_message(self) -> str:
        missing = []
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not self.anthropic_model:
            missing.append("ANTHROPIC_MODEL")
        if not self.live_enabled:
            missing.append("TUTOR_LIVE_ENABLED=1 (explicit opt-in)")
        if not missing:
            return ""
        return (
            "Live tutoring is not configured. Set " + ", ".join(missing) +
            " in your local .env file (copy .env.example), then restart the app. "
            "These are read only by the local Python server and are separate from any "
            "Claude Code or claude.ai credits. Until then you can use the library, "
            "search and saved sessions, and try the scripted demo mode "
            f"(\"{DEMO_LABEL}\")."
        )

    def public_dict(self) -> dict:
        """What the browser may see. Never includes the key itself."""
        return {
            "live_configured": self.live_configured,
            "live_setup_message": self.live_setup_message,
            "model_configured": bool(self.anthropic_model),
            "api_key_present": bool(self.anthropic_api_key),
            "live_enabled": self.live_enabled,
            "model": self.anthropic_model,   # a model ID is configuration, not a secret
            "live_limits": {"max_requests_per_day": self.live_max_requests_per_day,
                            "max_output_tokens": self.anthropic_max_tokens,
                            "max_retries": self.live_max_retries,
                            "max_input_chars": self.live_max_input_chars},
            "demo_label": DEMO_LABEL,
            "max_upload_mb": self.max_upload_bytes // (1024 * 1024),
            "host": self.host,
        }

    @classmethod
    def from_env(cls, environ=None, dotenv: bool = True) -> "Settings":
        if environ is None:
            if dotenv:
                load_dotenv(ROOT / ".env")
            environ = os.environ
        data_dir = Path(environ.get("TUTOR_DATA_DIR") or ROOT / "data").expanduser()
        if not data_dir.is_absolute():
            data_dir = (ROOT / data_dir).resolve()
        try:
            max_mb = float(environ.get("TUTOR_MAX_UPLOAD_MB") or 25)
        except ValueError:
            max_mb = 25
        max_tokens = _int(environ, "ANTHROPIC_MAX_TOKENS", 2048, 256, TOKENS_CEILING)
        try:
            port = int(environ.get("TUTOR_PORT") or 8000)
        except ValueError:
            port = 8000
        return cls(
            data_dir=data_dir,
            host=environ.get("TUTOR_HOST") or "127.0.0.1",
            port=port,
            max_upload_bytes=int(max_mb * 1024 * 1024),
            anthropic_api_key=(environ.get("ANTHROPIC_API_KEY") or None),
            anthropic_model=(environ.get("ANTHROPIC_MODEL") or None),
            anthropic_max_tokens=max_tokens,
            force_no_fts=_flag(environ.get("TUTOR_FORCE_NO_FTS")),
            live_enabled=_flag(environ.get("TUTOR_LIVE_ENABLED")),
            live_max_requests_per_day=_int(environ, "TUTOR_LIVE_MAX_REQUESTS_PER_DAY", 20, 0, 500),
            live_max_retries=_int(environ, "TUTOR_LIVE_MAX_RETRIES", 1, 0, 2),
            live_max_input_chars=_int(environ, "TUTOR_LIVE_MAX_INPUT_CHARS", 48000, 2000, 200000),
        )

"""`python -m app` — start the local server (localhost only by default)."""
import sys

import uvicorn

from .config import Settings


def main() -> None:
    s = Settings.from_env()
    if s.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: TUTOR_HOST={s.host} exposes this app beyond your machine. "
              "It has no accounts or authentication. Use 127.0.0.1 unless you know why not.",
              file=sys.stderr)
    mode = "LIVE tutoring available" if s.live_configured else "demo mode only (no ANTHROPIC_API_KEY/ANTHROPIC_MODEL)"
    print(f"Source-Grounded Tutor -> http://{s.host}:{s.port}   [{mode}]   data: {s.data_dir}")
    uvicorn.run("app.main:app_factory", factory=True, host=s.host, port=s.port, log_level="warning")


if __name__ == "__main__":
    main()

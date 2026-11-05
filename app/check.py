"""`python -m app.check` — report configuration WITHOUT printing secrets.

    python -m app.check            # config report only (no network)
    python -m app.check --ping     # ONE tiny live request, after you type 'yes'

The --ping request spends a small amount of your API balance. It is the only way this
project establishes that the key and model actually work; until one succeeds, nothing
should be described as tested or accessible.
"""
from __future__ import annotations

import argparse
import sys

from .config import Settings
from .db import Database
from .livecontrol import LiveGuard
from .providers import AnthropicProvider, GenRequest, ProviderError


def report(s: Settings, guard: LiveGuard, db: Database) -> list[str]:
    u = guard.summary()
    env_file = (s.data_dir.parent / ".env")
    return [
        f".env file found:        {'yes' if (__import__('pathlib').Path(__file__).resolve().parent.parent / '.env').is_file() else 'no'}",
        f"ANTHROPIC_API_KEY:      {'set (hidden)' if s.anthropic_api_key else 'NOT set'}",
        f"ANTHROPIC_MODEL:        {s.anthropic_model or 'NOT set'}",
        f"TUTOR_LIVE_ENABLED:     {'yes' if s.live_enabled else 'no (live calls refused)'}",
        f"live configured:        {'yes' if s.live_configured else 'no'}",
        f"API reachable:          {'yes (last ' + u['last_api_success'] + ')' if u['api_reachable'] else 'NO - no successful live HTTP request recorded yet'}",
        f"structured output:      {'yes (last ' + u['last_structured'] + ')' if u['structured_output'] else 'NO - no usable structured reply seen yet'}",
        f"citation checks passed: {'yes (last ' + u['last_citation_checks_passed'] + ')' if u['citation_checks_passed'] else 'NO - no reply has passed the mechanical citation checks yet'}",
        f"max requests / UTC day: {s.live_max_requests_per_day}  (used today: {u['requests_today']})",
        f"max output tokens/req:  {s.anthropic_max_tokens}  (hard ceiling 4096)",
        f"max retries:            {s.live_max_retries}  (each retry counts as a request)",
        f"max input chars:        {s.live_max_input_chars}",
        f"tokens reported today:  {u['input_tokens_today']} in / {u['output_tokens_today']} out",
        f"data directory:         {s.data_dir}",
        f"retrieval:              {db.retrieval_mode}",
        "These limits are brakes, not a dollar spending cap. Set billing limits with your provider.",
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.check")
    ap.add_argument("--ping", action="store_true", help="send ONE small live request (costs a little)")
    ap.add_argument("--yes", action="store_true", help="skip the interactive confirmation for --ping")
    args = ap.parse_args(argv)
    s = Settings.from_env()
    db = Database(s.db_path, force_no_fts=s.force_no_fts)
    guard = LiveGuard(db, s)
    print("\n".join(report(s, guard, db)))
    if not args.ping:
        return 0
    if not s.live_configured:
        print("\nCannot ping: " + s.live_setup_message)
        return 2
    if not args.yes:
        ans = input("\nThis sends ONE small request to Anthropic and uses a little of your API balance. Type 'yes' to continue: ")
        if ans.strip().lower() != "yes":
            print("Cancelled; nothing was sent.")
            return 1
    prov = AnthropicProvider(s.anthropic_api_key, s.anthropic_model, min(s.anthropic_max_tokens, 300),
                             guard=guard, max_retries=0)
    req = GenRequest(task="ping", system="You are a connectivity check. Answer only through the tool.",
                     messages=[{"role": "user", "content": "Return one coaching block whose text is: ok"}],
                     passages=[])
    try:
        out = prov.generate(req)
    except ProviderError as e:
        print(f"\nPing FAILED: {e.message}")
        return 1
    try:
        from .citations import normalize_blocks
        normalize_blocks(out)
        guard.mark(prov.last_call_id, structured=True)
        structured = True
    except ValueError:
        guard.mark(prov.last_call_id, structured=False)
        structured = False
    print("\nAPI request succeeded (key and model ID were accepted)."
          + (" The reply was valid structured output." if structured else " BUT the reply was NOT usable structured output."))
    print(f"Reply (truncated): {str(out)[:160]}")
    print("This says nothing about tutoring quality. Ask a real question about approved documents in the app; "
          "only a reply whose citations pass the mechanical checks counts as 'citation checks passed' "
          "(and even that does not show a passage supports a claim).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Model providers: a small interface, a deterministic demo provider, an Anthropic adapter.

Live calls only happen when the learner picks "live" for a session AND the server has
ANTHROPIC_API_KEY and ANTHROPIC_MODEL in its environment. The key never leaves this
process: it is not logged, stored in the database, or sent to the browser, and error
messages are redacted before they are returned.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .config import DEMO_LABEL, TOKENS_CEILING, Settings
from .errors import AppError

log = logging.getLogger("tutor.live")

BLOCK_TYPES = ["quote", "interpretation", "synthesis", "fiction", "coaching", "limits"]

SUBMIT_TOOL = {
    "name": "submit_response",
    "description": ("Submit the tutor reply as an ordered list of typed blocks. "
                    "This is the only way to answer."),
    "input_schema": {
        "type": "object",
        "properties": {"blocks": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": BLOCK_TYPES},
                "purpose": {"type": "string",
                            "description": "Exercise role of the block, only when instructed."},
                "text": {"type": "string"},
                "citations": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"passage_id": {"type": "string"},
                                   "quote": {"type": "string",
                                             "description": "Verbatim excerpt of that passage."}},
                    "required": ["passage_id"]}},
            },
            "required": ["type", "text"]}}},
        "required": ["blocks"],
    },
}


class ProviderError(AppError):
    pass


@dataclass
class GenRequest:
    task: str                     # chat | repair | exercise_* (see exercises.py)
    system: str
    messages: list[dict]          # bounded history + the current user turn (with evidence)
    passages: list[dict]          # allowed evidence snapshots for THIS turn
    context: dict = field(default_factory=dict)   # structured info (used by the demo provider)


class Provider(ABC):
    name = "abstract"
    is_live = False

    @property
    @abstractmethod
    def label(self) -> str: ...

    @abstractmethod
    def generate(self, req: GenRequest) -> dict:
        """Return {'blocks': [...]} (or raise ProviderError)."""


class MockProvider(Provider):
    """Deterministic, scripted, offline. Never calls the network."""
    name = "demo"
    is_live = False

    @property
    def label(self) -> str:
        return DEMO_LABEL

    def generate(self, req: GenRequest) -> dict:
        from . import demo_script
        return demo_script.generate(req)


class AnthropicProvider(Provider):
    """Anthropic Messages API adapter with bounded, counted requests.

    Every attempt (including retries and the citation-repair call) goes through
    ``LiveGuard.reserve`` first, so the daily request cap, input-size guard and usage
    logging apply to all of them. The SDK's own hidden retries are turned off
    (max_retries=0) so that every request this app sends is one it counted.
    """
    name = "anthropic"
    is_live = True

    def __init__(self, api_key: str, model: str, max_tokens: int = 2048, client=None,
                 guard=None, max_retries: int = 1, sleep=time.sleep):
        self._key = api_key
        self.model = model
        self.max_tokens = max(1, min(int(max_tokens), TOKENS_CEILING))
        self.guard = guard
        self.max_retries = max(0, min(int(max_retries), 2))
        self._sleep = sleep
        self.last_call_id = None          # id of the live_calls row behind the latest reply
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=60.0)
        self.client = client

    @property
    def label(self) -> str:
        return f"Live model: {self.model}"

    def _redact(self, text: str) -> str:
        return text.replace(self._key, "[redacted]") if self._key else text

    def _map(self, e: Exception) -> ProviderError:
        import anthropic
        if isinstance(e, anthropic.AuthenticationError):
            return ProviderError("The API rejected the configured ANTHROPIC_API_KEY "
                                 "(authentication failed). Check the key in your .env.", 502)
        if isinstance(e, anthropic.PermissionDeniedError):
            return ProviderError("The API key does not have permission for this request.", 502)
        if isinstance(e, anthropic.NotFoundError):
            return ProviderError("The API did not recognise the configured ANTHROPIC_MODEL. "
                                 "Check the model ID in your .env.", 502)
        if isinstance(e, anthropic.RateLimitError):
            return ProviderError("The API rate limit was hit. Wait a moment and try again.", 429)
        if isinstance(e, anthropic.APIConnectionError):
            return ProviderError("Could not reach the Anthropic API (network problem or timeout). "
                                 "Your message was not saved; try again.", 502)
        if isinstance(e, anthropic.BadRequestError):
            return ProviderError("The API rejected the request: "
                                 + self._redact(str(getattr(e, "message", "bad request")))[:300], 502)
        if isinstance(e, anthropic.APIStatusError):
            return ProviderError(f"The API returned an error (HTTP {getattr(e, 'status_code', '?')}).", 502)
        return ProviderError("The API call failed.", 502)

    @staticmethod
    def _retryable(e: Exception) -> bool:
        import anthropic
        if isinstance(e, (anthropic.APIConnectionError, anthropic.RateLimitError)):
            return True
        return isinstance(e, anthropic.APIStatusError) and getattr(e, "status_code", 0) >= 500

    def generate(self, req: GenRequest) -> dict:
        import anthropic

        chars = len(req.system) + sum(len(m["content"]) for m in req.messages)
        resp = None
        for attempt in range(self.max_retries + 1):
            call_id = self.guard.reserve(req.task, self.model, chars) if self.guard else None
            try:
                resp = self.client.messages.create(
                    model=self.model, max_tokens=self.max_tokens, system=req.system,
                    messages=req.messages, tools=[SUBMIT_TOOL],
                    tool_choice={"type": "tool", "name": "submit_response"})
            except anthropic.APIError as e:
                if self.guard:
                    self.guard.finish(call_id, "error", error=type(e).__name__
                                      + (f" {getattr(e, 'status_code', '')}" if hasattr(e, "status_code") else ""))
                if self._retryable(e) and attempt < self.max_retries:
                    self._sleep(1.5 * (attempt + 1))
                    continue
                raise self._map(e) from e
            if self.guard:
                self.guard.finish(call_id, "ok", usage=getattr(resp, "usage", None))
            self.last_call_id = call_id
            break
        if getattr(resp, "stop_reason", None) == "max_tokens":
            log.warning("live response hit the max_tokens limit (%s); output may be truncated", self.max_tokens)
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", "") == "tool_use":
                return dict(block.input)
        raise ProviderError("The model did not return a structured answer.", 502)


def make_provider_factory(settings: Settings, guard=None):
    def factory(kind: str) -> Provider:
        if kind == "demo":
            return MockProvider()
        if kind == "live":
            if not settings.live_configured:
                raise ProviderError(settings.live_setup_message, 400)
            return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model,
                                     settings.anthropic_max_tokens, guard=guard,
                                     max_retries=settings.live_max_retries)
        raise ProviderError("Unknown provider.", 400)
    return factory

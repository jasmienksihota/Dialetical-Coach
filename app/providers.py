"""Model providers: a small interface, a deterministic demo provider, an Anthropic adapter.

Live calls only happen when the learner picks "live" for a session AND the server has
ANTHROPIC_API_KEY and ANTHROPIC_MODEL in its environment. The key never leaves this
process: it is not logged, stored in the database, or sent to the browser, and error
messages are redacted before they are returned.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .config import DEMO_LABEL, Settings
from .errors import AppError

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
    name = "anthropic"
    is_live = True

    def __init__(self, api_key: str, model: str, max_tokens: int = 2048, client=None):
        self._key = api_key
        self.model = model
        self.max_tokens = max_tokens
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, max_retries=1, timeout=90.0)
        self.client = client

    @property
    def label(self) -> str:
        return f"Live model: {self.model}"

    def _redact(self, text: str) -> str:
        return text.replace(self._key, "[redacted]") if self._key else text

    def generate(self, req: GenRequest) -> dict:
        import anthropic

        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=req.system,
                messages=req.messages, tools=[SUBMIT_TOOL],
                tool_choice={"type": "tool", "name": "submit_response"})
        except anthropic.AuthenticationError as e:
            raise ProviderError("The API rejected the configured ANTHROPIC_API_KEY "
                                "(authentication failed). Check the key in your .env.", 502) from e
        except anthropic.PermissionDeniedError as e:
            raise ProviderError("The API key does not have permission for this request.", 502) from e
        except anthropic.NotFoundError as e:
            raise ProviderError("The API did not recognise the configured ANTHROPIC_MODEL. "
                                "Check the model ID in your .env.", 502) from e
        except anthropic.RateLimitError as e:
            raise ProviderError("The API rate limit was hit. Wait a moment and try again.", 429) from e
        except anthropic.APIConnectionError as e:
            raise ProviderError("Could not reach the Anthropic API (network problem or timeout). "
                                "Your message was not saved; try again.", 502) from e
        except anthropic.BadRequestError as e:
            raise ProviderError("The API rejected the request: "
                                + self._redact(str(getattr(e, "message", "bad request")))[:300], 502) from e
        except anthropic.APIStatusError as e:
            raise ProviderError(f"The API returned an error (HTTP {getattr(e, 'status_code', '?')}).", 502) from e
        except anthropic.APIError as e:
            raise ProviderError("The API call failed.", 502) from e
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", "") == "tool_use":
                return dict(block.input)
        raise ProviderError("The model did not return a structured answer.", 502)


def make_provider_factory(settings: Settings):
    def factory(kind: str) -> Provider:
        if kind == "demo":
            return MockProvider()
        if kind == "live":
            if not settings.live_configured:
                raise ProviderError(settings.live_setup_message, 400)
            return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model,
                                     settings.anthropic_max_tokens)
        raise ProviderError("Unknown provider.", 400)
    return factory

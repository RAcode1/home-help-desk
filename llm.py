"""
llm.py

One place for Claude calls: structured JSON output, refusal handling, and
cost tracking. Every feature asks Claude for a fixed shape (a Pydantic
model) and validates the answer before using it.
"""

from anthropic import Anthropic, transform_schema
from dotenv import load_dotenv
from pydantic import BaseModel, TypeAdapter

from config import MODEL_PRICING

load_dotenv()
_client = None


def client():
    """Create the API client on first use, so demo mode never needs a key."""
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


def json_format(output_model):
    """Structured-output format for a Pydantic model."""
    return {
        "type": "json_schema",
        "schema": transform_schema(TypeAdapter(output_model).json_schema()),
    }


# Models that support a server-side fallback: if a safety check declines
# the request (it can happen with scam text), the API retries it on another
# model inside the same call.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}


def ask_structured(model, system, content, output_model, effort="low", max_tokens=16000):
    """Send one request and return (parsed output or None, usage).

    Returns None when Claude declines (stop_reason "refusal"), so callers
    can fall back safely instead of crashing.
    """
    request = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": effort, "format": json_format(output_model)},
    )
    if model in FALLBACK_MODELS:
        message = client().beta.messages.create(
            **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
        )
    else:
        message = client().messages.create(**request)

    if message.stop_reason == "refusal":
        return None, message.usage
    if message.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off (max_tokens). Try fewer items per request.")

    text = next((block.text for block in message.content if block.type == "text"), "")
    return output_model.model_validate_json(text), message.usage


class CostTracker:
    """Adds up token usage across calls and converts it to dollars."""

    def __init__(self):
        self.calls = []

    def add(self, model, usage):
        if usage is not None:
            self.calls.append((model, usage.input_tokens, usage.output_tokens))

    @property
    def dollars(self):
        total = 0.0
        for model, tokens_in, tokens_out in self.calls:
            price_in, price_out = MODEL_PRICING.get(model, (0, 0))
            total += tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out
        return total

    def summary(self):
        tokens_in = sum(call[1] for call in self.calls)
        tokens_out = sum(call[2] for call in self.calls)
        return f"{len(self.calls)} Claude calls, {tokens_in:,} tokens in, {tokens_out:,} out, about ${self.dollars:.3f}"

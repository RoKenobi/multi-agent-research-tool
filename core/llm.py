import logging
import os

import anthropic

from core.tracing import generation

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"

# Models that accept server-side refusal fallbacks ("default" routing).
_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")


# (input, output) USD per million tokens — Anthropic list prices as of 2026-09.
_PRICES_PER_MTOK = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class LLMRefusalError(RuntimeError):
    pass


def create_client() -> tuple:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set — add it to .env")
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY; retries 429/5xx twice by default
    model = os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    return client, model


def complete(
    client,
    model: str,
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 16000,
    effort: str | None = None,
    name: str = "claude",
):
    """Send one user message and return (text, response).

    Current Claude models think adaptively by default, so the response may start
    with thinking blocks — only text blocks are joined into the returned string.
    """
    kwargs = {}
    if system:
        kwargs["system"] = system
    if effort and not model.startswith("claude-haiku"):
        kwargs["output_config"] = {"effort": effort}
    if model in _FALLBACK_MODELS:
        # If a safety classifier declines, the API re-runs the request on a fallback model.
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"

    messages = [{"role": "user", "content": prompt}]
    trace_input = ([{"role": "system", "content": system}] if system else []) + messages

    with generation(
        name,
        model=model,
        input=trace_input,
        model_parameters={"max_tokens": max_tokens, "effort": effort},
    ) as gen:
        try:
            response = client.beta.messages.create(
                model=model, max_tokens=max_tokens, messages=messages, **kwargs,
            )
        except Exception as e:
            gen.update(level="ERROR", status_message=str(e))
            raise

        text = "".join(block.text for block in response.content if block.type == "text")
        usage = {"input": response.usage.input_tokens, "output": response.usage.output_tokens}
        gen.update(
            model=response.model,  # differs from `model` when a refusal fallback served the request
            output=text,
            usage_details=usage,
            cost_details=estimate_cost(response.model, usage),
            metadata={"stop_reason": response.stop_reason},
            level="WARNING" if response.stop_reason in ("refusal", "max_tokens") else None,
        )

    if response.stop_reason == "refusal":
        raise LLMRefusalError(f"Model declined the request: {getattr(response, 'stop_details', None)}")
    if response.stop_reason == "max_tokens":
        logger.warning("Response hit max_tokens=%d and is truncated", max_tokens)

    return text, response


def estimate_cost(model: str, usage: dict[str, int]) -> dict[str, float] | None:
    """USD cost from list prices, so Langfuse shows cost even for models it doesn't price yet."""
    prices = _PRICES_PER_MTOK.get(model)
    if not prices:
        return None
    cost = {
        "input": usage["input"] * prices[0] / 1_000_000,
        "output": usage["output"] * prices[1] / 1_000_000,
    }
    cost["total"] = cost["input"] + cost["output"]
    return cost

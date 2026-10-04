import logging
import os

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"

# Models that accept server-side refusal fallbacks ("default" routing).
_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")


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

    response = client.beta.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )

    if response.stop_reason == "refusal":
        raise LLMRefusalError(f"Model declined the request: {getattr(response, 'stop_details', None)}")
    if response.stop_reason == "max_tokens":
        logger.warning("Response hit max_tokens=%d and is truncated", max_tokens)

    text = "".join(block.text for block in response.content if block.type == "text")
    return text, response

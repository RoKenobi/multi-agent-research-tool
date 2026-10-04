import logging
import os

import anthropic

logger = logging.getLogger(__name__)


class LLMRefusalError(RuntimeError):
    pass


def create_client() -> tuple:
    # AnthropicBedrock reads AWS_BEARER_TOKEN_BEDROCK from the environment itself.
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = anthropic.AnthropicBedrock(aws_region=region)
    model = os.environ.get(
        "ANTHROPIC_MODEL",
        "us.anthropic.claude-sonnet-5-20251101-v1:0",
    )
    return client, model


def complete(client, model: str, prompt: str, *, system: str | None = None, max_tokens: int = 16000):
    """Send one user message and return (text, response).

    Current Claude models think adaptively by default, so the response may start
    with thinking blocks — only text blocks are joined into the returned string.
    """
    kwargs = {"system": system} if system else {}
    response = client.messages.create(
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

import os
import logging
from langfuse import Langfuse

logger = logging.getLogger(__name__)
_client: Langfuse | None = None


def init_langfuse() -> None:
    global _client
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        logger.warning("LANGFUSE_PUBLIC_KEY not set — tracing disabled")
        return
    _client = Langfuse()
    logger.info("Langfuse tracing enabled")


def flush() -> None:
    if _client:
        _client.flush()

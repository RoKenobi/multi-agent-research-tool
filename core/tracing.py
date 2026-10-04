import contextlib
import functools
import logging
import os

from langfuse import get_client, observe as _langfuse_observe, propagate_attributes

logger = logging.getLogger(__name__)
_enabled = False


def init_langfuse() -> None:
    global _enabled
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        logger.warning("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set — tracing disabled")
        return
    get_client()
    _enabled = True
    logger.info("Langfuse tracing enabled")


def observe(name: str):
    """Langfuse @observe that becomes a plain call when tracing is disabled.

    Decorators are applied at import time, before .env is loaded, so the
    enabled check has to happen per call.
    """
    def decorator(fn):
        traced = _langfuse_observe(name=name)(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return (traced if _enabled else fn)(*args, **kwargs)

        return wrapper

    return decorator


def trace_attributes(trace_name: str, metadata: dict[str, str]):
    """Context manager naming the current trace (no-op when disabled)."""
    if _enabled:
        return propagate_attributes(trace_name=trace_name, metadata=metadata)
    return contextlib.nullcontext()


class _NoopGeneration:
    def update(self, **kwargs) -> None:
        pass


@contextlib.contextmanager
def generation(name: str, **kwargs):
    """Record an LLM call as a Langfuse generation (model, prompt, output, tokens, cost).

    Yields an object with .update(...); a no-op stand-in when tracing is disabled.
    """
    if not _enabled:
        yield _NoopGeneration()
        return
    with get_client().start_as_current_observation(name=name, as_type="generation", **kwargs) as gen:
        yield gen


def update_span(**kwargs) -> None:
    """Attach input/output/metadata to the current observation (no-op when disabled)."""
    if _enabled:
        get_client().update_current_span(**kwargs)


def flush() -> None:
    if _enabled:
        get_client().flush()

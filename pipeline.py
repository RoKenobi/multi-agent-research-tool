import sys
import logging
from pathlib import Path

from core.config import load_env, load_config
from core.bedrock import create_client
from core.tracing import init_langfuse, flush, observe, trace_attributes, update_span
from core.obsidian import write_brief
from agents import signal_agent, arxiv_agent, synthesizer

# Task Scheduler redirects stdout to a file using the ANSI code page; the
# box-drawing characters below would raise UnicodeEncodeError there.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@observe(name="deep_signal_pipeline")
def run_topic(topic: str, cfg: dict, client, model: str) -> Path:
    with trace_attributes(trace_name=f"deep_signal | {topic}", metadata={"topic": topic}):
        # Stage 1: Signal Agent
        logger.info("━━━ [1/3] Signal Agent ━━━")
        signal = signal_agent.run(topic, cfg)

        # Stage 2: ArXiv Agent
        logger.info("━━━ [2/3] ArXiv Agent ━━━")
        papers = arxiv_agent.run(topic, signal, client, model, cfg)

        # Stage 3: Synthesizer
        logger.info("━━━ [3/3] Synthesizer ━━━")
        brief = synthesizer.run(topic, signal, papers, client, model, cfg)

        # Write to Obsidian
        path = write_brief(brief, topic, cfg)
        logger.info("Saved → %s", path)

        update_span(output={"path": str(path), "papers_found": len(papers)})
        return path


def main() -> int:
    load_env()
    cfg = load_config()
    client, model = create_client()
    init_langfuse()

    # CLI: python pipeline.py "Physical AI"
    # Scheduled: python pipeline.py  (uses config.yaml scheduled_topics)
    topics = sys.argv[1:] if len(sys.argv) > 1 else cfg.get("scheduled_topics", ["Physical AI"])

    logger.info("Deep Signal Pipeline starting — %d topic(s)", len(topics))
    logger.info("Model: %s", model)

    results, failures = [], []
    try:
        for topic in topics:
            logger.info("═══ Topic: %s ═══", topic)
            # One bad topic must not cost the rest of the morning's briefs.
            try:
                results.append((topic, run_topic(topic, cfg, client, model)))
            except Exception:
                logger.exception("Topic '%s' failed", topic)
                failures.append(topic)
    finally:
        flush()

    print("\n─── Done ───")
    for topic, path in results:
        print(f"  {topic}  →  {path}")
    for topic in failures:
        print(f"  {topic}  →  FAILED (see log above)")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

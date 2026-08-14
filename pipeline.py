import sys
import logging
from pathlib import Path
from langfuse.decorators import observe, langfuse_context

from core.config import load_env, load_config
from core.bedrock import create_client
from core.tracing import init_langfuse, flush
from core.obsidian import write_brief
from agents import signal_agent, arxiv_agent, synthesizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@observe(name="deep_signal_pipeline")
def run_topic(topic: str, cfg: dict, client, model: str) -> Path:
    langfuse_context.update_current_trace(
        name=f"deep_signal | {topic}",
        metadata={"topic": topic},
    )

    # Stage 1: Signal Agent
    logger.info("━━━ [1/3] Signal Agent ━━━")
    signal = signal_agent.run(topic, cfg)

    # Stage 2: ArXiv Agent
    logger.info("━━━ [2/3] ArXiv Agent ━━━")
    cfg["_current_topic"] = topic
    papers = arxiv_agent.run(signal, client, model, cfg)

    # Stage 3: Synthesizer
    logger.info("━━━ [3/3] Synthesizer ━━━")
    brief = synthesizer.run(topic, signal, papers, client, model)

    # Write to Obsidian
    path = write_brief(brief, topic, cfg)
    logger.info("Saved → %s", path)

    langfuse_context.update_current_trace(
        output={"path": str(path), "papers_found": len(papers)},
    )
    return path


def main() -> None:
    load_env()
    cfg = load_config()
    client, model = create_client()
    init_langfuse()

    # CLI: python pipeline.py "Physical AI"
    # Scheduled: python pipeline.py  (uses config.yaml scheduled_topics)
    topics = sys.argv[1:] if len(sys.argv) > 1 else cfg.get("scheduled_topics", ["Physical AI"])

    logger.info("Deep Signal Pipeline starting — %d topic(s)", len(topics))
    logger.info("Model: %s", model)

    results = []
    try:
        for topic in topics:
            logger.info("═══ Topic: %s ═══", topic)
            path = run_topic(topic, cfg, client, model)
            results.append((topic, path))
    finally:
        flush()

    print("\n─── Done ───")
    for topic, path in results:
        print(f"  {topic}  →  {path}")


if __name__ == "__main__":
    main()

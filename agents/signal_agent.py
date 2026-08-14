import os
import sys
import subprocess
import logging
from pathlib import Path
from langfuse.decorators import observe, langfuse_context

logger = logging.getLogger(__name__)


@observe(name="signal_agent")
def run(topic: str, cfg: dict) -> str:
    root: Path = cfg["_root"]
    script = root / cfg["last30days_script"]
    cwd = root / cfg["last30days_cwd"]

    if not script.exists():
        logger.error(
            "last30days script not found at %s — run setup first:\n"
            "  cd skills && git clone https://github.com/mvanhorn/last30days-skill last30days\n"
            "  cd last30days && uv sync",
            script,
        )
        langfuse_context.update_current_observation(
            metadata={"error": "script_not_found", "path": str(script)}
        )
        return ""

    # Use the venv Python if available (uv creates .venv inside the skill dir)
    venv_python = cwd / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = cwd / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(sys.executable)

    logger.info("Signal Agent: querying last30days for '%s'", topic)

    try:
        result = subprocess.run(
            [str(venv_python), str(script), topic, f"--emit={cfg.get('last30days_emit', 'compact')}"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=cfg.get("signal_timeout_sec", 90),
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        logger.warning("Signal Agent timed out for topic '%s'", topic)
        langfuse_context.update_current_observation(
            metadata={"error": "timeout", "topic": topic}
        )
        return ""

    if result.returncode != 0:
        logger.warning("Signal Agent returned non-zero exit for '%s': %s", topic, result.stderr[:300])
        langfuse_context.update_current_observation(
            metadata={"error": result.stderr[:500], "return_code": result.returncode}
        )
        return ""

    output = result.stdout.strip()
    langfuse_context.update_current_observation(
        input={"topic": topic},
        output=output[:500],
        metadata={"output_length": len(output)},
    )
    logger.info("Signal Agent: got %d chars of signal", len(output))
    return output

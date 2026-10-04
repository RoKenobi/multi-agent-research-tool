import re
import yaml
from pathlib import Path
from datetime import date


def write_brief(content: str, topic: str, cfg: dict) -> Path:
    vault: Path = cfg["_vault"]
    today = date.today().isoformat()

    slug = re.sub(r"[^\w\s-]", "", topic.lower()).strip()
    slug = re.sub(r"[\s]+", "-", slug) or "untitled"

    folder = vault / "Deep Signal" / slug
    folder.mkdir(parents=True, exist_ok=True)

    file_path = folder / f"{today}.md"

    frontmatter_data = {
        "date": today,
        "topic": topic,
        "tags": ["deep-signal", "ai-research", slug],
        "generated_by": "deep-signal-pipeline",
    }
    frontmatter = yaml.dump(frontmatter_data, default_flow_style=False, allow_unicode=True)
    full_content = f"---\n{frontmatter}---\n\n{content}"

    file_path.write_text(full_content, encoding="utf-8")
    return file_path

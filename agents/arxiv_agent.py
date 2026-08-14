import io
import json
import logging
import re
import tarfile
import time
import urllib.request
from pathlib import Path

import arxiv
import fitz  # PyMuPDF fallback
from langfuse.decorators import observe, langfuse_context

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """\
From the trending tech content below, extract the exact titles of any academic papers, \
research frameworks, or named AI models/systems mentioned.

Return ONLY a valid JSON array of strings. Example: ["Attention Is All You Need", "RT-2"]
If nothing found, return: []

Content:
{signal_text}"""


@observe(name="arxiv_agent")
def run(signal_text: str, client, model: str, cfg: dict) -> list[dict]:
    topic = cfg.get("_current_topic", "Physical AI")

    if signal_text:
        names = _extract_entities(signal_text, client, model)
        logger.info("ArXiv Agent: extracted entities: %s", names)
    else:
        names = []

    # If signal extraction found nothing, fall back to searching the topic directly
    if not names:
        logger.info("ArXiv Agent: no entities found, falling back to topic search")
        names = [topic]

    papers = _search_arxiv(names, cfg.get("max_papers", 3))
    logger.info("ArXiv Agent: found %d papers", len(papers))

    for paper in papers:
        logger.info("ArXiv Agent: fetching LaTeX source for %s", paper["id"])
        paper["content"] = _fetch_latex_source(paper["id"]) or _extract_pdf_text(paper["pdf_url"])

    langfuse_context.update_current_observation(
        input={"entities": names},
        metadata={"papers_found": len(papers)},
    )
    return papers


def _extract_entities(signal_text: str, client, model: str) -> list[str]:
    try:
        response = client.messages.create(
            model=model,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": EXTRACT_PROMPT.format(signal_text=signal_text[:3000]),
            }],
        )
        text = response.content[0].text.strip()
        match = re.search(r"\[.*?\]", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        logger.warning("Entity extraction failed: %s", e)
    return []


def _search_arxiv(names: list[str], max_papers: int) -> list[dict]:
    client = arxiv.Client(delay_seconds=3.0)
    papers = []
    seen = set()

    for name in names:
        if len(papers) >= max_papers:
            break
        try:
            results = list(client.results(
                arxiv.Search(query=name, max_results=2, sort_by=arxiv.SortCriterion.Relevance)
            ))
            for r in results:
                arxiv_id = r.entry_id.split("/")[-1]
                if arxiv_id not in seen and len(papers) < max_papers:
                    seen.add(arxiv_id)
                    papers.append({
                        "id": arxiv_id,
                        "title": r.title,
                        "authors": [a.name for a in r.authors[:3]],
                        "abstract": r.summary.replace("\n", " "),
                        "pdf_url": r.pdf_url,
                        "published": str(r.published.date()) if r.published else "",
                        "content": None,
                    })
        except Exception as e:
            logger.warning("ArXiv search failed for '%s': %s", name, e)

        time.sleep(1)

    return papers


def _fetch_latex_source(arxiv_id: str) -> str:
    """Download and extract the main .tex file from ArXiv source tarball."""
    url = f"https://arxiv.org/src/{arxiv_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DeepSignalResearch/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            tex_files = []
            for member in tar.getmembers():
                if member.name.endswith(".tex"):
                    f = tar.extractfile(member)
                    if f:
                        text = f.read().decode("utf-8", errors="ignore")
                        if len(text) > 500:
                            tex_files.append(text)

            if tex_files:
                # largest .tex file is almost always the main paper
                main = max(tex_files, key=len)
                return main[:15000]

    except Exception as e:
        logger.warning("LaTeX fetch failed for %s: %s", arxiv_id, e)

    return ""


def _extract_pdf_text(pdf_url: str) -> str:
    """PyMuPDF fallback: extract plain text directly from the PDF."""
    if not pdf_url:
        return ""
    try:
        req = urllib.request.Request(pdf_url, headers={"User-Agent": "DeepSignalResearch/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        doc = fitz.open(stream=data, filetype="pdf")
        pages = []
        for page in doc:
            pages.append(page.get_text())
            if len("\n".join(pages)) > 12000:
                break
        doc.close()
        return "\n".join(pages)[:12000]

    except Exception as e:
        logger.warning("PDF text extraction failed for %s: %s", pdf_url, e)

    return ""

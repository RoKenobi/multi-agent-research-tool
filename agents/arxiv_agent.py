import gzip
import io
import json
import logging
import re
import tarfile
import time
import urllib.request

import arxiv
import pymupdf  # PDF fallback

from core.llm import complete
from core.tracing import observe, update_span

logger = logging.getLogger(__name__)

USER_AGENT = "DeepSignalResearch/1.0"
MAX_ENTITIES = 8

EXTRACT_PROMPT = """\
From the trending tech content below, extract the exact titles of any academic papers, \
research frameworks, or named AI models/systems mentioned.

Return ONLY a valid JSON array of strings. Example: ["Attention Is All You Need", "RT-2"]
If nothing found, return: []

Content:
{signal_text}"""


@observe(name="arxiv_agent")
def run(topic: str, signal_text: str, client, model: str, cfg: dict) -> list[dict]:
    names = _extract_entities(signal_text, client, model) if signal_text else []
    logger.info("ArXiv Agent: extracted entities: %s", names)

    # If signal extraction found nothing, fall back to searching the topic directly
    if not names:
        logger.info("ArXiv Agent: no entities found, falling back to topic search")
        names = [topic]

    papers = _search_arxiv(names, cfg.get("max_papers", 3), cfg.get("arxiv_category_filter", "cat:cs.*"))
    logger.info("ArXiv Agent: found %d papers", len(papers))

    char_budget = cfg.get("paper_char_budget", 20000)
    for paper in papers:
        logger.info("ArXiv Agent: fetching LaTeX source for %s", paper["id"])
        latex = _fetch_latex_source(paper["id"], char_budget)
        if latex:
            paper["content"], paper["content_type"] = latex, "latex"
        else:
            text = _extract_pdf_text(paper["pdf_url"], char_budget)
            paper["content"], paper["content_type"] = (text, "pdf_text") if text else (None, None)

    update_span(
        input={"topic": topic, "entities": names},
        metadata={"papers_found": len(papers)},
    )
    return papers


def _extract_entities(signal_text: str, client, model: str) -> list[str]:
    try:
        text, _ = complete(
            client, model,
            EXTRACT_PROMPT.format(signal_text=signal_text[:6000]),
            max_tokens=2048,
            effort="low",
        )
        return parse_entity_list(text)
    except Exception as e:
        logger.warning("Entity extraction failed: %s", e)
    return []


def parse_entity_list(text: str) -> list[str]:
    """Pull the first JSON array of strings out of a model reply; dedupe, cap length."""
    start = text.find("[")
    while start != -1:
        try:
            value, _ = json.JSONDecoder().raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("[", start + 1)
            continue
        if isinstance(value, list):
            seen, names = set(), []
            for item in value:
                if isinstance(item, str) and item.strip() and item.strip().lower() not in seen:
                    seen.add(item.strip().lower())
                    names.append(item.strip())
            return names[:MAX_ENTITIES]
        start = text.find("[", start + 1)
    return []


def _search_arxiv(names: list[str], max_papers: int, category: str = "") -> list[dict]:
    client = arxiv.Client(delay_seconds=3.0)
    papers = []
    seen = set()
    # Short model names are ambiguous ("RT-2" is also an astrophysics instrument).
    scope = f" AND {category}" if category else ""

    for name in names:
        if len(papers) >= max_papers:
            break
        try:
            # Exact title match first — a named paper is one paper, so keep only the top hit.
            phrase = '"{}"'.format(name.replace('"', ""))
            results = list(client.results(arxiv.Search(query=f"ti:{phrase}{scope}", max_results=1)))
            if not results:
                results = list(client.results(arxiv.Search(
                    query=f"all:{phrase}{scope}", max_results=2, sort_by=arxiv.SortCriterion.Relevance,
                )))
            for r in results:
                arxiv_id = r.get_short_id()
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
                        "content_type": None,
                    })
        except Exception as e:
            logger.warning("ArXiv search failed for '%s': %s", name, e)

        time.sleep(1)

    return papers


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _fetch_latex_source(arxiv_id: str, char_budget: int) -> str:
    try:
        return extract_main_tex(_download(f"https://arxiv.org/src/{arxiv_id}"), char_budget)
    except Exception as e:
        logger.warning("LaTeX fetch failed for %s: %s", arxiv_id, e)
    return ""


def extract_main_tex(raw: bytes, char_budget: int) -> str:
    """Return the paper body from an arXiv source download.

    arXiv serves a gzipped tarball for multi-file papers, a gzipped single .tex
    for one-file papers, and sometimes just a PDF.
    """
    try:
        data = gzip.decompress(raw)
    except OSError:
        data = raw

    files: dict[str, str] = {}
    buf = io.BytesIO(data)
    if tarfile.is_tarfile(buf):
        buf.seek(0)
        with tarfile.open(fileobj=buf) as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.endswith(".tex"):
                    f = tar.extractfile(member)
                    if f:
                        name = member.name.removeprefix("./")
                        files[name] = strip_comments(f.read().decode("utf-8", errors="ignore"))
    elif not data.startswith(b"%PDF"):
        files["main.tex"] = strip_comments(data.decode("utf-8", errors="ignore"))

    if not files:
        return ""
    # Prefer the file that actually declares the document; else the largest.
    mains = [n for n, t in files.items() if "\\documentclass" in t] or list(files)
    main = max(mains, key=lambda n: len(files[n]))
    body = clean_latex(inline_inputs(files[main], files))
    if len(body) < 500:
        return ""
    if len(body) > char_budget:
        logger.info("LaTeX body is %d chars, truncating to %d", len(body), char_budget)
    return body[:char_budget]


_INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")


def inline_inputs(tex: str, files: dict[str, str], depth: int = 0) -> str:
    r"""Replace \input{x} / \include{x} with the referenced file from the tarball.

    Many papers keep every section in its own file, so the main .tex alone is
    just front matter.
    """
    if depth > 5:
        return tex

    def resolve(match: re.Match) -> str:
        ref = match.group(1).strip().removeprefix("./")
        for candidate in (ref, f"{ref}.tex"):
            if candidate in files:
                return inline_inputs(files[candidate], files, depth + 1)
        return match.group(0)

    return _INPUT_RE.sub(resolve, tex)


def strip_comments(tex: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", tex)  # keep escaped \%


def clean_latex(tex: str) -> str:
    """Drop the preamble, bibliography and comments so the budget is spent on content."""
    tex = strip_comments(tex)
    begin = tex.find("\\begin{document}")
    if begin != -1:
        tex = tex[begin + len("\\begin{document}"):]
    for marker in ("\\begin{thebibliography}", "\\bibliography{", "\\end{document}"):
        end = tex.find(marker)
        if end != -1:
            tex = tex[:end]
    return re.sub(r"\n\s*\n+", "\n\n", tex).strip()


def _extract_pdf_text(pdf_url: str, char_budget: int) -> str:
    """PyMuPDF fallback: extract plain text directly from the PDF."""
    if not pdf_url:
        return ""
    try:
        doc = pymupdf.open(stream=_download(pdf_url), filetype="pdf")
        pages, total = [], 0
        for page in doc:
            text = page.get_text()
            pages.append(text)
            total += len(text)
            if total > char_budget:
                break
        doc.close()
        return "\n".join(pages)[:char_budget]

    except Exception as e:
        logger.warning("PDF text extraction failed for %s: %s", pdf_url, e)

    return ""

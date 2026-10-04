import gzip
import io
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline
from agents import arxiv_agent, synthesizer
from agents.arxiv_agent import clean_latex, extract_main_tex, parse_entity_list
from core.llm import LLMRefusalError, complete
from core.obsidian import write_brief

BODY = "We propose a method. " * 40 + r"$$ L = \sum_i \ell(x_i) $$ costs 5\% less."
PAPER = (
    "\\documentclass{article}\n\\usepackage{amsmath}\n% secret comment\n"
    f"\\begin{{document}}\n{BODY}\n\\bibliography{{refs}}\n\\end{{document}}\n"
)


# --- entity parsing ---------------------------------------------------------

def test_parse_entity_list_handles_brackets_inside_strings():
    assert parse_entity_list('Sure: ["RT-2 [v2]", "Octo"]') == ["RT-2 [v2]", "Octo"]


def test_parse_entity_list_dedupes_and_drops_non_strings():
    assert parse_entity_list('["Octo", "octo", 3, "", "Pi0"]') == ["Octo", "Pi0"]


def test_parse_entity_list_garbage_returns_empty():
    assert parse_entity_list("no json [here") == []


# --- LaTeX extraction -------------------------------------------------------

def _tar_gz(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_clean_latex_strips_preamble_comments_and_bibliography():
    out = clean_latex(PAPER)
    assert "usepackage" not in out and "secret comment" not in out
    assert "bibliography" not in out
    assert r"\sum_i" in out and r"5\% less" in out


def test_extract_main_tex_prefers_documentclass_file_over_larger_include():
    big_include = "x" * 50000
    raw = _tar_gz({"appendix.tex": big_include, "main.tex": PAPER})
    assert extract_main_tex(raw, 20000).startswith("We propose")


def test_extract_main_tex_accepts_gzipped_single_file():
    assert r"\sum_i" in extract_main_tex(gzip.compress(PAPER.encode()), 20000)


def test_extract_main_tex_rejects_pdf_and_respects_budget():
    assert extract_main_tex(gzip.compress(b"%PDF-1.5 ..."), 20000) == ""
    assert len(extract_main_tex(gzip.compress(PAPER.encode()), 600)) == 600


# --- LLM response handling --------------------------------------------------

class FakeClient:
    def __init__(self, response):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response))


def _response(blocks, stop_reason="end_turn"):
    return SimpleNamespace(
        content=blocks, stop_reason=stop_reason, stop_details=None,
        usage=SimpleNamespace(input_tokens=1, output_tokens=2),
    )


def test_complete_skips_thinking_blocks():
    resp = _response([
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text="hello"),
    ])
    text, _ = complete(FakeClient(resp), "m", "hi")
    assert text == "hello"


def test_complete_raises_on_refusal():
    with pytest.raises(LLMRefusalError):
        complete(FakeClient(_response([], stop_reason="refusal")), "m", "hi")


def test_synthesizer_prompt_includes_paper_body():
    seen = {}

    def create(**kw):
        seen.update(kw)
        return _response([SimpleNamespace(type="text", text="# brief")])

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    paper = {"title": "T", "authors": ["A"], "id": "1", "abstract": "abs",
             "content": "X" * 10000 + "FORMULA", "content_type": "latex"}
    out = synthesizer.run("Topic", "signal", [paper], client, "m", {})
    assert out == "# brief"
    assert "FORMULA" in seen["messages"][0]["content"]


# --- Obsidian output --------------------------------------------------------

def test_write_brief_slug_and_frontmatter(tmp_path):
    path = write_brief("body", "Vision-Language Action (VLA)!", {"_vault": tmp_path})
    assert path.parent.name == "vision-language-action-vla"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n") and "topic: Vision-Language Action (VLA)!" in text


def test_write_brief_symbol_only_topic_gets_fallback_slug(tmp_path):
    assert write_brief("b", "???", {"_vault": tmp_path}).parent.name == "untitled"


# --- pipeline orchestration -------------------------------------------------

def test_main_continues_after_topic_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "load_env", lambda: None)
    monkeypatch.setattr(pipeline, "load_config", lambda: {})
    monkeypatch.setattr(pipeline, "create_client", lambda: (None, "m"))
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "bad", "good"])

    def fake_run_topic(topic, cfg, client, model):
        if topic == "bad":
            raise RuntimeError("boom")
        return tmp_path / "good.md"

    monkeypatch.setattr(pipeline, "run_topic", fake_run_topic)
    assert pipeline.main() == 1  # non-zero so the scheduler log shows a failure


def test_arxiv_agent_falls_back_to_topic(monkeypatch):
    searched = {}
    monkeypatch.setattr(arxiv_agent, "_search_arxiv", lambda names, n, cat: searched.setdefault("names", names) and [])
    assert arxiv_agent.run("Physical AI", "", None, "m", {}) == []
    assert searched["names"] == ["Physical AI"]


def test_extract_main_tex_inlines_section_files():
    main = (
        "\\documentclass{article}\n\\begin{document}\n\\input{sections/intro}\n"
        "% \\input{sections/unused}\n\\end{document}\n"
    )
    raw = _tar_gz({"./main.tex": main, "./sections/intro.tex": BODY, "./sections/unused.tex": "NOPE" * 200})
    out = extract_main_tex(raw, 20000)
    assert out.startswith("We propose") and "NOPE" not in out


def test_complete_request_params_depend_on_model():
    calls = []

    def create(**kw):
        calls.append(kw)
        return _response([SimpleNamespace(type="text", text="ok")])

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    complete(client, "claude-opus-5-5", "hi", effort="low")
    complete(client, "claude-haiku-4-5", "hi", effort="low")
    assert calls[0]["fallbacks"] == "default" and calls[0]["output_config"] == {"effort": "low"}
    assert "fallbacks" not in calls[1] and "output_config" not in calls[1]

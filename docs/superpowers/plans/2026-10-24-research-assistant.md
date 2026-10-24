# Embodied AI Research Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the daily buzz-brief pipeline into an on-demand research assistant: give it an embodied-AI topic, and it finds papers and repos, breaks papers down, grows a per-topic knowledge base and gap map in Obsidian, and proposes novelty-checked research ideas.

**Architecture:** Plain-Python orchestration in `pipeline.py` over five agents (arXiv scout, GitHub scout, reader, ideas, critic) with one bounded critic→scout loop. Agents are pure functions over plain dicts; all fetching is done in `sources/`, all persistence in `core/kb.py`. Every LLM call is a `claude -p` subprocess on the user's Claude plan, traced as a Langfuse generation.

**Tech Stack:** Python 3.12, Claude Code CLI 2.1.309 (`claude -p`), `arxiv`, PyMuPDF, `urllib` (GitHub REST, Semantic Scholar Graph API), Langfuse v4 (self-hosted), PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-10-23-research-assistant-design.md`

## Global Constraints

- Branch `research-assistant`. Old pipeline stays on `master`; remove `agents/signal_agent.py`, `agents/synthesizer.py`, `core/obsidian.py`, last30days config on this branch.
- No Anthropic API key and no `anthropic` package: every LLM call is `claude -p` via `core/llm.py`.
- `claude -p` flags, verified 2026-10-24: `--output-format json --model <m> --effort <e> --tools "" --no-session-persistence --safe-mode --strict-mcp-config --disable-slash-commands --system-prompt <s>`; prompt goes on **stdin** (Windows command lines cap at ~32K chars). `--safe-mode` cuts per-call overhead from ~68K to ~0.6K input tokens; **never use `--bare`** (it skips the keychain and fails with "Not logged in").
- Resolve the executable with `shutil.which("claude")` (it is `C:\Users\mroha\.local\bin\claude` on this machine).
- Langfuse is optional: unreachable server or missing keys must never fail a run. Cost is recorded as `total_cost_usd` and labelled `"api_equivalent_estimate"`, not a bill.
- Models: fast = `claude-sonnet-5-5` at effort `low` (queries, ranking, repo filtering); deep = `claude-opus-5-5` at effort `high` (reader, ideas, critic). Both from `config.yaml`.
- Caps from `config.yaml`: `max_new_papers: 15` per run total, of which `followup_papers: 5` reserved for critic follow-ups; `max_critic_rounds: 2`; `max_repos: 10`; `llm_concurrency: 2`. Inbox papers are the user's own and are not capped.
- Lab context (prompts and ranking): robots `Unitree G1`, `AgiBot X2`; simulator `MuJoCo` by default but not fixed — never treat other simulators as irrelevant.
- arXiv scope default: `(cat:cs.RO OR cat:cs.LG OR cat:cs.AI OR cat:cs.CV)`.
- Vault layout per topic: `<vault>/Research/<slug>/{papers/<id>.md, repos/<owner>__<repo>.md, gap-map.md, ideas/YYYY-MM-DD.md, inbox/, inbox/processed/, index.json}`.
- No topic is hard-coded anywhere; topic always comes from the CLI.
- Tests make no network calls and spend nothing (monkeypatch `subprocess.run`, `urllib.request.urlopen`, and `core.llm.complete`).

## Review Focus

- **`claude` missing or not logged in** → the run exits before any fetching with a message saying to install Claude Code or run `claude` then `/login`. Test in Task 1.
- **Plan usage limit hit mid-run** → run stops, everything already read stays in `index.json`, exit code 2, and the next run skips those papers. Test in Task 8.
- **LLM reply wraps JSON in prose or code fences, or is malformed** → JSON is still extracted; a reader reply that stays unparseable after one retry skips that paper (not indexed, retried next run). Tests in Tasks 1 and 6.
- **Same topic typed differently** (`"Humanoid WBC"`, `"humanoid  wbc"`) → same folder. Test in Task 4.
- **Paper with no LaTeX source and no PDF text** → breakdown is made from the abstract and marked `content_type: "abstract"`. Test in Task 6.

---

## File Structure

| File | Responsibility |
|---|---|
| `core/llm.py` (rewrite) | `complete()` over `claude -p`; `LLMError`, `LLMUsageLimitError`; `check_cli()` |
| `core/jsonparse.py` (new) | Extract the first JSON array/object from model text |
| `core/kb.py` (new) | Per-topic knowledge base: slug, index, notes, gap map, ideas report, inbox |
| `core/config.py` (modify) | Load new config keys; vault guard unchanged |
| `core/tracing.py` | Unchanged |
| `sources/arxiv_source.py` (new, code moved from `agents/arxiv_agent.py`) | arXiv search over queries, fetch body (LaTeX → PDF → none) |
| `sources/github_source.py` (new) | GitHub repo search with rate-limit pacing |
| `sources/semantic_scholar.py` (new) | References and citations of an arXiv paper |
| `agents/scout_arxiv.py` (new) | Queries → candidates → rank → capped new papers |
| `agents/scout_github.py` (new) | Queries + per-paper lookups → filtered repos |
| `agents/reader.py` (new) | One paper → breakdown dict |
| `agents/ideas.py` (new) | Knowledge base digest → ranked ideas |
| `agents/critic.py` (new) | Ideas → verdicts, re-rank, follow-up queries |
| `pipeline.py` (rewrite) | CLI, graph, loop, caps, usage-limit stop |
| `tests/test_*.py` | One test file per module above |

## Shared data shapes (plain dicts; every task uses these exact keys)

- **Paper:** `id` (arXiv short id like `"2307.15818"`, or `"local-<slug>"` for inbox PDFs), `title`, `authors: list[str]`, `abstract`, `pdf_url`, `published` (ISO date or `""`), `source` (`"arxiv" | "semantic_scholar" | "inbox" | "followup"`), `content: str | None`, `content_type: "latex" | "pdf_text" | "abstract" | None`.
- **Breakdown** (reader output): `problem: str`, `approach: str`, `setup: {embodiment, simulator, sim_or_real, training_cost}` (all `str`), `results: str`, `limitations: {stated: list[str], unstated: list[str]}`, `future_work: list[str]`, `code_and_data: list[str]`, `key_references: list[{title: str, arxiv_id: str | None}]`, `relevance: str`, `approaches: list[str]`, `capabilities: list[str]` (lowercase short tags), `lab_fit: int` (0–3).
- **Repo:** `full_name` (`"owner/repo"`), `url`, `description`, `stars: int`, `updated` (ISO date), `language`, `linked_papers: list[str]` (paper ids), `why_relevant: str`.
- **Idea:** `title`, `improvement`, `gap`, `evidence_papers: list[str]`, `closest_prior_work: list[str]`, `novelty` (`"novel" | "partly done" | "done" | "unclear"`), `novelty_evidence: str`, `feasibility: str`, `rank: int` (1 = best).

---

### Task 1: LLM backend over `claude -p`, plus JSON extraction

**Files:**
- Rewrite: `core/llm.py`
- Create: `core/jsonparse.py`
- Modify: `requirements.txt` (remove `anthropic`)
- Test: `tests/test_llm.py`, `tests/test_jsonparse.py`

**Interfaces:**
- Produces:
  - `check_cli() -> str` returns the `claude` path or raises `SystemExit` with text containing `"Claude Code"` and `"/login"`. It runs one tiny `complete()` call ("Reply with exactly: ok") to prove login.
  - `complete(prompt: str, *, model: str, system: str, effort: str = "low", name: str = "claude", timeout: int = 600) -> LLMResult`
  - `@dataclass LLMResult: text: str; model: str; usage: dict[str, int]; cost_usd: float | None`
  - `class LLMError(RuntimeError)`, `class LLMUsageLimitError(LLMError)`
  - `parse_json(text: str, expect: type[list] | type[dict]) -> list | dict | None` in `core/jsonparse.py`

- [ ] **Step 1: Write failing tests** in `tests/test_llm.py`, monkeypatching `core.llm.subprocess.run` and `core.llm.shutil.which`:
  - `test_complete_builds_cli_command`: assert argv contains `-p`, `--output-format json`, `--model claude-opus-5-5`, `--effort high`, `--tools ""`, `--no-session-persistence`, `--safe-mode`, `--strict-mcp-config`, `--disable-slash-commands`, `--system-prompt <given>`, does **not** contain `--bare`, and the prompt is passed as `input=` not in argv.
  - `test_complete_parses_json_result`: stdout `{"result": "hi", "is_error": false, "total_cost_usd": 0.01, "usage": {"input_tokens": 3, "cache_creation_input_tokens": 600, "cache_read_input_tokens": 0, "output_tokens": 2}, "modelUsage": {"claude-opus-5-5": {}}}` → `text == "hi"`, `model == "claude-opus-5-5"`, `usage == {"input": 603, "output": 2}`, `cost_usd == 0.01`.
  - `test_complete_raises_usage_limit`: `is_error: true`, `result: "Claude usage limit reached. Your limit will reset at 5pm"` → `LLMUsageLimitError`.
  - `test_complete_raises_llm_error_on_other_errors`: non-zero return code with empty stdout → `LLMError` (not the usage-limit subclass); `is_error: true` with `result: "Not logged in · Please run /login"` → `LLMError` whose message contains `/login`.
  - `test_check_cli_missing_exits`: `which` returns `None` → `SystemExit` mentioning `Claude Code`.
  - `test_complete_records_generation_when_tracing_enabled`: port the existing test from `tests/test_pipeline.py`; assert the generation gets `usage_details={"input": 603, "output": 2}`, `cost_details={"total": 0.01}` and `metadata["cost_basis"] == "api_equivalent_estimate"`.
- [ ] **Step 2: Write failing tests** in `tests/test_jsonparse.py`: port the three `parse_entity_list` tests from `tests/test_pipeline.py` to `parse_json(..., list)`, and add `test_parse_json_object_in_code_fence` (```` ```json\n{"a": 1}\n``` ```` → `{"a": 1}`), `test_parse_json_skips_wrong_type` (`'[1] then {"a": 2}'` with `expect=dict` → `{"a": 2}`), `test_parse_json_returns_none_on_garbage`.
- [ ] **Step 3: Run** `.venv/Scripts/python -m pytest tests/test_llm.py tests/test_jsonparse.py -v` — expect FAIL (import errors).
- [ ] **Step 4: Implement `core/jsonparse.py`.** Generalize the `raw_decode` scanner from `agents/arxiv_agent.py:parse_entity_list`: scan from each `[` or `{` (whichever matches `expect`), return the first decoded value of type `expect`. No dedupe or capping here; callers do that.
- [ ] **Step 5: Implement `core/llm.py`.** `subprocess.run(argv, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=timeout)`. Usage-limit detection: `is_error` true and the `result` text matches `re.compile(r"usage limit|rate limit|limit (?:reached|will reset)", re.I)`. `usage["input"]` = sum of `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`. Model = first key of `modelUsage`, else the requested model. Wrap the call in `core.tracing.generation(name, model=..., input=[{"role": "system", ...}, {"role": "user", ...}], model_parameters={"effort": effort})`, and set `level="ERROR"` on failures. Delete `_PRICES_PER_MTOK`, `estimate_cost`, `create_client`, fallbacks and the `anthropic` import. Remove `anthropic` from `requirements.txt`.
- [ ] **Step 6: Run** the same pytest command — expect PASS.
- [ ] **Step 7: Trim `tests/test_pipeline.py`.** Delete the tests that use removed APIs or were ported here (`test_parse_entity_list_*`, `test_complete_*`, `test_estimate_cost_uses_list_prices`, `test_synthesizer_*`, `test_main_continues_after_topic_failure`, `test_arxiv_agent_falls_back_to_topic`, `test_write_brief_*`) and their now-unused imports. Leave the LaTeX tests for Task 2 to move. The old `pipeline.py` is expected to be broken until Task 8 rewrites it.
- [ ] **Step 8: Commit** `git add core/llm.py core/jsonparse.py requirements.txt tests/ && git commit -m "Run LLM calls through claude -p on the Claude plan"`.

---

### Task 2: Sources (arXiv, GitHub, Semantic Scholar)

**Files:**
- Create: `sources/__init__.py`, `sources/arxiv_source.py`, `sources/github_source.py`, `sources/semantic_scholar.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Produces:
  - `arxiv_source.search(queries: list[str], *, per_query: int, category: str) -> list[dict]` returns Paper dicts with `source="arxiv"`, `content=None`, deduped by id in query order.
  - `arxiv_source.fetch_by_ids(ids: list[str]) -> list[dict]` (Paper dicts; used for inbox links and Semantic Scholar hits).
  - `arxiv_source.fetch_content(paper: dict, char_budget: int) -> None` sets `content`/`content_type` in place: LaTeX, then PDF text, then `abstract` with `content_type="abstract"`.
  - `arxiv_source.extract_main_tex`, `inline_inputs`, `strip_comments`, `clean_latex`, `pdf_text_from_bytes(data: bytes, char_budget: int) -> str` (moved; the last is also used for inbox PDFs).
  - `github_source.search_repos(query: str, *, per_page: int, token: str | None) -> list[dict]` returns Repo dicts with `linked_papers=[]`, `why_relevant=""`.
  - `github_source.pause(token: str | None) -> None` sleeps 6.5 s without a token, 2.1 s with one (search API: 10/min unauthenticated, 30/min with a token).
  - `semantic_scholar.neighbors(arxiv_id: str, *, limit: int) -> list[str]` returns arXiv ids of references plus citations (deduped, without the input id); returns `[]` on any HTTP error.

- [ ] **Step 1: Write failing tests** in `tests/test_sources.py`:
  - Move the six LaTeX tests from `tests/test_pipeline.py` (`clean_latex…`, `extract_main_tex…` ×4) and point them at `sources.arxiv_source`.
  - `test_search_builds_scoped_query`: monkeypatch `arxiv.Client.results` to record `Search.query`; `search(["humanoid stairs"], per_query=8, category="(cat:cs.RO OR cat:cs.LG)")` → query == `'all:"humanoid stairs" AND (cat:cs.RO OR cat:cs.LG)'`; two queries returning the same id → one paper.
  - `test_fetch_content_falls_back_to_abstract`: LaTeX and PDF fetchers both return `""` → `content == paper["abstract"]`, `content_type == "abstract"`.
  - `test_github_search_parses_items`: fake `urlopen` returns `{"items": [{"full_name": "a/b", "html_url": "https://github.com/a/b", "description": null, "stargazers_count": 5, "pushed_at": "2026-09-01T00:00:00Z", "language": "Python"}]}` → `[{"full_name": "a/b", ..., "description": "", "stars": 5, "updated": "2026-09-01", "linked_papers": [], "why_relevant": ""}]`; with `token="t"` the request has header `Authorization: Bearer t`; URL contains `q=` (URL-encoded), `sort=stars`, `per_page=`.
  - `test_semantic_scholar_neighbors_extracts_arxiv_ids`: fake response `{"references": [{"externalIds": {"ArXiv": "2101.00001"}}, {"externalIds": {}}], "citations": [{"externalIds": {"ArXiv": "2201.00002"}}]}` → `["2101.00001", "2201.00002"]`; `HTTPError` → `[]`.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_sources.py -v` — expect FAIL.
- [ ] **Step 3: Implement.** Copy the code from `agents/arxiv_agent.py`, unchanged where possible (`agents/arxiv_agent.py` itself is deleted in Task 8). Rename `_extract_pdf_text` to download plus `pdf_text_from_bytes`. Delete the moved LaTeX tests from `tests/test_pipeline.py`. `search` uses `all:"<q>"` with the category ANDed, `sort_by=Relevance`, and `arxiv.Client(delay_seconds=3.0)`. Semantic Scholar endpoint: `https://api.semanticscholar.org/graph/v1/paper/arXiv:{id}?fields=references.externalIds,citations.externalIds&limit={limit}`. Every request sends the `User-Agent` header `ResearchAssistant/1.0`.
- [ ] **Step 4: Run** the pytest command — expect PASS.
- [ ] **Step 5: Commit** `git commit -m "Add arXiv, GitHub and Semantic Scholar sources"`.

---

### Task 3: Config

**Files:**
- Modify: `core/config.py`, `config.yaml`, `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `load_config() -> dict` with the existing `_root`/`_vault` plus every key below, with defaults filled when absent: `research_folder="Research"`, `lab={"robots": ["Unitree G1", "AgiBot X2"], "simulators": ["MuJoCo"]}`, `models={"fast": "claude-sonnet-5-5", "deep": "claude-opus-5-5"}`, `effort={"fast": "low", "deep": "high"}`, `arxiv_category_filter="(cat:cs.RO OR cat:cs.LG OR cat:cs.AI OR cat:cs.CV)"`, `arxiv_results_per_query=8`, `max_new_papers=15`, `followup_papers=5`, `max_critic_rounds=2`, `max_repos=10`, `paper_char_budget=40000`, `llm_concurrency=2`, `llm_timeout_sec=600`. `GITHUB_TOKEN` is read from env by callers.

- [ ] **Step 1: Write failing test** `test_load_config_fills_defaults` (tmp `config.yaml` containing only `vault_path` pointing at `tmp_path`; monkeypatch `core.config.ROOT`) → asserts the defaults above; `test_load_config_keeps_vault_guard` → missing vault raises `SystemExit`.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_config.py -v` — expect FAIL.
- [ ] **Step 3: Implement** with a `DEFAULTS` dict merged one level deep for `lab`, `models` and `effort`. Rewrite `config.yaml` to list every key explicitly with short comments; remove `scheduled_topics`, `max_papers`, `signal_*` and `last30days_*`. In `.env.example`, remove `ANTHROPIC_*`, `XAI_API_KEY`, `GOOGLE_API_KEY` and `BRAVE_API_KEY`, and add `GITHUB_TOKEN=` with the comment `# Optional — raises GitHub search limit from 10 to 30/min`.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git commit -m "Config for the research assistant"`.

---

### Task 4: Knowledge base

**Files:**
- Create: `core/kb.py`
- Test: `tests/test_kb.py`

**Interfaces:**
- Consumes: Paper / Breakdown / Repo / Idea shapes; `cfg["_vault"]`, `cfg["research_folder"]`.
- Produces:
  - `slugify(topic: str) -> str`: lowercase, strip non-word characters, collapse whitespace and hyphens to one `-`, fallback `"untitled"`.
  - `class KnowledgeBase(cfg: dict, topic: str)` with attributes `root: Path` and `slug: str`, and methods:
    - `has_paper(paper_id: str) -> bool`, `has_repo(full_name: str) -> bool`
    - `add_paper(paper: dict, breakdown: dict) -> Path` writes `papers/<id>.md` and updates the index, then saves.
    - `add_repo(repo: dict) -> Path` writes `repos/<owner>__<repo>.md`, then saves.
    - `known_tags() -> dict[str, list[str]]` returns `{"approaches": [...], "capabilities": [...]}`, sorted and unique.
    - `digest() -> list[dict]`: per paper `{id, title, problem, approach, setup, limitations, future_work, relevance, approaches, capabilities, lab_fit}`.
    - `repos_digest() -> list[dict]`: `{full_name, description, stars, linked_papers, why_relevant}`.
    - `write_gap_map() -> Path`
    - `last_ideas() -> list[dict]` (most recent run's ideas, `[]` if none)
    - `write_ideas(ideas: list[dict], meta: dict) -> Path` writes `ideas/YYYY-MM-DD.md` (suffix `-2`, `-3`… if it exists) and appends to `index["ideas_history"]`.
    - `ingest_inbox() -> list[dict]`: `*.pdf` → Paper with `id="local-<slugify(stem)>"`, `source="inbox"`, `content` from `pdf_text_from_bytes`, `content_type="pdf_text"`, `title=stem`. `links.txt` → arXiv ids matched by `r"(\d{4}\.\d{4,5})(?:v\d+)?"` → `arxiv_source.fetch_by_ids` with `source="inbox"`. Skips ids already in the index.
    - `mark_inbox_done(paper: dict) -> None` moves the PDF to `inbox/processed/`. For a link it removes that line from `links.txt` and appends it to `inbox/processed/links.txt`.
- `index.json` schema: `{"topic": str, "slug": str, "papers": {id: {"title", "note", "added", "source", "digest": {...}}}, "repos": {full_name: {...repo}}, "ideas_history": [{"date", "file", "ideas": [...]}]}`. Writes go to `index.json.tmp` and then `os.replace` (crash-safe).

- [ ] **Step 1: Write failing tests** in `tests/test_kb.py` (with `tmp_path` as vault):
  - `test_slugify_same_topic_different_spelling`: `"Humanoid WBC"`, `"humanoid  wbc"` and `" Humanoid-WBC! "` → all `"humanoid-wbc"`; `"!!!"` → `"untitled"`.
  - `test_add_paper_writes_note_and_index`: note has YAML frontmatter with `arxiv_id`, `title`, `tags` including the slug and the approach/capability tags; the body has headings `## Problem`, `## Approach`, `## Setup`, `## Results`, `## Limitations`, `## Future work`, `## Code & data`, `## Key references`, `## Relevance`, and links `https://arxiv.org/abs/<id>` for arXiv papers. A reloaded `KnowledgeBase` → `has_paper` is true.
  - `test_gap_map_marks_empty_cells`: paper A `approaches=["rl"]`, `capabilities=["stairs"]`; paper B `["mpc"]`/`["push recovery"]` → table rows `rl`, `mpc`; columns `push recovery`, `stairs`; cell (rl, stairs) contains `[[papers/A|` and cell (rl, push recovery) is `—`.
  - `test_ingest_inbox_pdf_and_links`: one PDF (build it with `pymupdf` in the test) and `links.txt` containing `https://arxiv.org/abs/2307.15818v2` (monkeypatch `fetch_by_ids`) → two Papers with `source == "inbox"`; after `mark_inbox_done` the PDF is in `inbox/processed/` and `links.txt` no longer has the line.
  - `test_write_ideas_does_not_overwrite_same_day`: two calls → `YYYY-MM-DD.md` and `YYYY-MM-DD-2.md`; `last_ideas()` returns the second batch.
  - `test_index_survives_reload_and_is_atomic`: after `add_repo`, `index.json` parses as JSON and `index.json.tmp` doesn't exist.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_kb.py -v` — expect FAIL.
- [ ] **Step 3: Implement `core/kb.py`.** Note rendering uses `yaml.dump(..., allow_unicode=True)` frontmatter like the old `core/obsidian.py:write_brief`. Gap map: rows and columns are the sorted union of tags across indexed papers; each cell holds Obsidian links `[[papers/<id>|<id>]]` joined by `, `, or `—` when empty. Ideas report: one `## <rank>. <title>` section per idea, with the novelty verdict bold, evidence papers as `[[papers/<id>]]` links, and a run summary on top from `meta` (`papers_read`, `repos_found`, `critic_rounds`, `stopped_early`).
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git commit -m "Add per-topic knowledge base with gap map and inbox"`.

---

### Task 5: Scouts

**Files:**
- Create: `agents/scout_arxiv.py`, `agents/scout_github.py`
- Test: `tests/test_scouts.py`

**Interfaces:**
- Consumes: `complete`, `parse_json`, `arxiv_source.search/fetch_by_ids`, `semantic_scholar.neighbors`, `github_source.search_repos/pause`, `KnowledgeBase.has_paper/has_repo`.
- Produces:
  - `scout_arxiv.run(topic: str, kb: KnowledgeBase, cfg: dict, *, limit: int, queries: list[str] | None = None) -> list[dict]` returns new Papers (`content=None`), at most `limit`, best first. `source` is `"followup"` when `queries` is given.
  - `scout_github.run(topic: str, kb: KnowledgeBase, cfg: dict, *, papers: list[dict], queries: list[str] | None = None) -> list[dict]` returns new Repos, at most `cfg["max_repos"]`, with `linked_papers` and `why_relevant` filled.

- [ ] **Step 1: Write failing tests** (monkeypatch `agents.scout_arxiv.complete` etc. with fakes returning `LLMResult`):
  - `test_scout_arxiv_generates_queries_when_none`: the fake fast-model reply `'["q1","q2"]'` → `search` is called with `["q1", "q2"]`; the prompt contains the topic and both lab robots and `MuJoCo`; the call uses `model=cfg["models"]["fast"]`, `effort="low"`.
  - `test_scout_arxiv_skips_known_and_caps`: 5 candidates, 1 already in the KB, rank reply lists ids in a new order, `limit=2` → the first 2 ranked unknown ids, in rank order. Ids invented by the ranker are ignored, and candidates the ranker omits come after ranked ones.
  - `test_scout_arxiv_followup_uses_given_queries`: `queries=["x"]` → no query-generation call, and every result has `source == "followup"`.
  - `test_scout_arxiv_adds_semantic_scholar_neighbors`: `neighbors` returns one new id → `fetch_by_ids` is called with it and the paper is in the ranked candidate pool.
  - `test_scout_github_links_papers_and_filters`: a per-paper search with query `"<arxiv_id>" in:readme` returns repo `a/b` → `linked_papers == [id]`; the filter reply `[{"full_name": "a/b", "why_relevant": "…"}]` keeps only `a/b`; `pause` is called between searches.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_scouts.py -v` — expect FAIL.
- [ ] **Step 3: Implement.** arXiv flow: queries (fast model, ask for 4–6 search queries as a JSON list) → `search` → `neighbors(limit=20)` of the top 3 arXiv hits → `fetch_by_ids` for new ones (`source="semantic_scholar"`) → drop `kb.has_paper` → if the pool is bigger than `limit`, rank with the fast model (input: id, title, abstract trimmed to 600 chars; lab context; reply: JSON list of ids). GitHub flow: queries (fast model, 3–4 queries) + one `in:readme` lookup per paper (only papers with arXiv-style ids) → dedupe → drop `kb.has_repo` → filter with the fast model (reply: JSON list of `{full_name, why_relevant}`) → cap. Every search failure is logged and skipped, never raised.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git commit -m "Add arXiv and GitHub scouts"`.

---

### Task 6: Reader

**Files:**
- Create: `agents/reader.py`
- Test: `tests/test_reader.py`

**Interfaces:**
- Consumes: `complete`, `parse_json`, `arxiv_source.fetch_content`, `KnowledgeBase.known_tags`.
- Produces: `reader.run(paper: dict, topic: str, kb: KnowledgeBase, cfg: dict) -> dict` (Breakdown); `class ReaderError(RuntimeError)`. It calls `fetch_content(paper, cfg["paper_char_budget"])` first when `paper["content"] is None`.

- [ ] **Step 1: Write failing tests:**
  - `test_reader_returns_breakdown_with_all_keys`: a valid JSON reply → every Breakdown key is present; tags are lowercased and stripped; `lab_fit` is clamped to 0–3.
  - `test_reader_prompt_has_content_lab_and_known_tags`: the prompt contains the paper body, `Unitree G1`, `AgiBot X2`, `MuJoCo`, the sentence telling the model other simulators are fine, and the existing tags from `known_tags()` with an instruction to reuse them; the call uses the deep model and effort.
  - `test_reader_retries_once_then_raises`: two unparseable replies → `ReaderError`, exactly 2 `complete` calls; unparseable then valid → success.
  - `test_reader_abstract_only_paper`: `fetch_content` leaves `content_type == "abstract"` → the prompt says only the abstract was available, and the breakdown's `results` is passed through unchanged.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_reader.py -v` — expect FAIL.
- [ ] **Step 3: Implement.** The system prompt states the 9-point breakdown and the JSON schema, with the exact keys of the Breakdown shape. Ask the model to list unstated limitations separately, and to prefer existing tags. Missing keys in a parsed reply are filled with empty values of the right type; only an unparseable reply triggers the retry.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git commit -m "Add paper reader"`.

---

### Task 7: Ideas and Critic

**Files:**
- Create: `agents/ideas.py`, `agents/critic.py`
- Test: `tests/test_ideas_critic.py`

**Interfaces:**
- Consumes: `complete`, `parse_json`, `KnowledgeBase.digest/repos_digest/last_ideas`, the gap map text (`kb.root / "gap-map.md"`).
- Produces:
  - `ideas.run(topic: str, kb: KnowledgeBase, cfg: dict) -> list[dict]` returns 5–8 Ideas with `novelty="unclear"`, ranked.
  - `critic.run(topic: str, ideas: list[dict], kb: KnowledgeBase, cfg: dict, *, final: bool) -> tuple[list[dict], list[str]]` returns `(ideas with novelty/novelty_evidence/feasibility/rank updated, follow-up queries)`. Queries are `[]` when `final` is true, and are capped at 4.

- [ ] **Step 1: Write failing tests:**
  - `test_ideas_prompt_contains_digest_gap_map_repos_and_last_ideas`: the prompt includes a digest paper's `problem`, the gap-map table text, a repo `full_name`, and a previous idea title marked as "already proposed"; full LaTeX is not included (assert a sentinel string from `paper["content"]` is absent).
  - `test_ideas_normalizes_and_ranks`: a reply with ranks `[3, 1]` → returned sorted by rank, missing keys filled, `novelty == "unclear"`.
  - `test_critic_returns_followups_only_for_unclear`: a reply with one `"unclear"` idea carrying `search_queries: ["a", "b"]` and one `"novel"` idea → queries `["a", "b"]`; `final=True` → queries `[]`.
  - `test_critic_drops_unknown_verdicts`: novelty `"maybe"` → `"unclear"`; ideas the critic omits keep their previous values.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_ideas_critic.py -v` — expect FAIL.
- [ ] **Step 3: Implement.** The Ideas system prompt asks for improvements to methods or systems in the topic (not one big idea), each tied to a gap-map cell or a stated/unstated limitation with evidence paper ids, and avoids repeating previous ideas unless it refines them. The Critic judges each idea against the digest: `done` and `partly done` must cite paper ids. `feasibility` notes G1/X2 fit and sim portability (MuJoCo default, others fine). The reply is a JSON list matched to ideas by `title`.
- [ ] **Step 4: Run** — expect PASS.
- [ ] **Step 5: Commit** `git commit -m "Add ideas and critic agents"`.

---

### Task 8: Pipeline orchestration

**Files:**
- Rewrite: `pipeline.py`
- Delete: `agents/signal_agent.py`, `agents/synthesizer.py`, `agents/arxiv_agent.py`, `core/obsidian.py`, `tests/test_pipeline.py` (its tests were moved in Tasks 1–2)
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `run(topic: str, cfg: dict) -> RunResult`; `main(argv: list[str] | None = None) -> int`. `@dataclass RunResult: ideas_path: Path | None; papers_read: int; repos_found: int; critic_rounds: int; stopped_early: str | None`. Exit codes: 0 success, 1 failure, 2 stopped on usage limit (partial results kept).

- [ ] **Step 1: Write failing tests** in `tests/test_run.py`, with all agents monkeypatched to fakes on a `tmp_path` vault:
  - `test_run_order_and_caps`: initial `scout_arxiv.run` gets `limit == max_new_papers - followup_papers` (10); the critic in round 1 returns queries → follow-up scout gets `limit == followup_papers` (5) and those queries; the round-2 critic is called with `final=True`; `critic_rounds == 2`; `ideas.run` is called once; the gap map is written before `ideas.run`.
  - `test_run_skips_followup_when_no_queries`: the critic returns `[]` → one critic round, no follow-up scout.
  - `test_reader_failure_skips_paper`: the reader raises `ReaderError` for one of two papers → only the other is indexed; the run still succeeds.
  - `test_usage_limit_stops_and_resumes`: the reader raises `LLMUsageLimitError` on the 2nd of 3 papers → `main` returns 2, paper 1 is in `index.json`, and the ideas report isn't written. A second `run` with a working reader is offered the same 3 papers by the fake scout and reads only papers 2 and 3 (the scout fake honours `kb.has_paper`, mirroring the real one).
  - `test_inbox_papers_read_uncapped_and_marked_done`: 3 inbox papers with `max_new_papers=1` → all 3 are read, `mark_inbox_done` is called for each.
  - `test_main_requires_topic`: `main([])` → returns 1 and prints usage containing `python pipeline.py "<topic>"`.
  - `test_main_checks_cli_first`: `check_cli` raises `SystemExit` → no scout is called.
- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_run.py -v` — expect FAIL.
- [ ] **Step 3: Implement `run`:**
  1. `kb = KnowledgeBase(cfg, topic)`; inbox papers = `kb.ingest_inbox()`.
  2. `papers = inbox + scout_arxiv.run(..., limit=max_new_papers - followup_papers)`; `repos = scout_github.run(..., papers=papers)`.
  3. `_read_all(papers)`: reader calls in a `ThreadPoolExecutor(max_workers=cfg["llm_concurrency"])`, each submitted as `contextvars.copy_context().run(reader.run, ...)` so the Langfuse spans nest under the run. `kb.add_paper` and `kb.mark_inbox_done` run on the main thread as futures complete. `ReaderError` is logged and skipped. `LLMUsageLimitError` cancels pending futures and re-raises.
  4. `kb.add_repo` for each repo; `kb.write_gap_map()`.
  5. `ideas = ideas.run(...)`.
  6. Loop `for round in range(1, max_critic_rounds + 1)`: `final = round == max_critic_rounds`; `ideas, queries = critic.run(..., final=final)`; break if `not queries`; else run the follow-up scouts (arXiv with `limit=followup_papers`, GitHub with the same queries), read, add, rewrite the gap map.
  7. `kb.write_ideas(ideas, meta)`.

  The whole run is wrapped in `@observe(name="research_run")` + `trace_attributes(trace_name=f"research | {topic}", metadata={"topic": topic})`, and each stage in a span named after it. `main`: keep the UTF-8 stdout reconfigure and logging setup; `load_env`, `load_config`, `check_cli`, `init_langfuse`; on `LLMUsageLimitError`, log `"Stopped: Claude plan usage limit reached. Progress is saved; run the same command again after the limit resets."`, rewrite the gap map, and return 2. `flush()` is always called in `finally`. Print a summary (ideas file path, papers read, repos, critic rounds).
- [ ] **Step 4: Run** the full suite `.venv/Scripts/python -m pytest -v` — expect all PASS.
- [ ] **Step 5: Commit** `git commit -m "Orchestrate the research assistant graph"`.

---

### Task 9: Docs and live smoke run

**Files:**
- Modify: `README.md`, `setup.md`
- Test: manual live run (spends a small amount of plan usage)

- [ ] **Step 1: Rewrite `README.md`** for the new tool: what it does (embodied-AI topic → papers, repos, breakdowns, gap map, ranked novelty-checked ideas), the five-agent mermaid graph with the loop, the vault layout, the inbox, `claude -p` on the Claude plan (no API key; `--safe-mode` and why), lab context in `config.yaml`, the config table matching Task 3, and Langfuse (keep the existing "Self-hosting Langfuse" section). Remove the last30days, the 8 AM scheduler instructions and the API-cost table. State that the old daily brief lives on `master`. `setup.md`: install, `claude` login check (`claude -p "hi"`), `.env` (Langfuse + optional `GITHUB_TOKEN`), `vault_path`, first run.
- [ ] **Step 2: Live smoke run** with small caps: `max_new_papers: 3`, `followup_papers: 1`, `max_repos: 3` via a temporary `config.yaml` edit (revert after): `.venv/Scripts/python pipeline.py "humanoid whole-body control"`. Expected: exit 0; `<vault>/Research/humanoid-whole-body-control/` contains 2–3 `papers/*.md` with all 9 headings filled, `gap-map.md` with a non-empty table, `ideas/<today>.md` with ≥5 ranked ideas each carrying a novelty verdict; Langfuse at `http://192.168.50.68:3000` shows trace `research | humanoid whole-body control` with generations nested under stage spans. Re-run the same command → the log says the known papers were skipped, and no paper is re-read.
- [ ] **Step 3: Revert the cap edit, commit and push** `git add README.md setup.md && git commit -m "Document the research assistant" && git push`.

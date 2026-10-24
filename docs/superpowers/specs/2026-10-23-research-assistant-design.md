# Embodied AI Research Assistant: design

Date: 2026-10-23 · Branch: `research-assistant`

## Intent

The user is joining a research lab and must find a paper they can write, in
**embodied AI** (the umbrella: humanoids, locomotion, whole-body control,
manipulation, VLA models, sim-to-real, and so on). The paper comes out of
taking an existing method or system and **making it better**, so the value is
in finding what is *not* done yet, and in several concrete improvements rather
than one "unique thing".

Topics are examples, not the scope. Whole-body control (WBC) for humanoids is
the first topic the user has in mind; stair climbing, push recovery and
balancing are examples of directions inside it.

They need to read far more papers than they can by hand. Given any embodied-AI
topic, the tool reads the literature and code for them, breaks each paper down
well, keeps everything it has learned between runs, and proposes ranked,
novelty-checked research ideas.

This replaces the current daily "community buzz → brief" pipeline on this
branch. The old tool stays on `master`.

## Goals

1. Given a research topic (e.g. "humanoid whole-body control"), find the
   relevant papers (arXiv) and code (GitHub).
2. Break every paper down into a fixed, useful structure (below).
3. Keep a **knowledge base per topic** that grows across runs; later runs build
   on earlier ones instead of starting over.
4. Maintain a **gap map** per topic across all its papers: approach ×
   capability, so empty cells (unexplored combinations) are visible.
5. Propose **several ranked improvements/research ideas** for the topic's
   methods or systems, each checked against the literature for "has this been
   done?" and feasibility.
6. Let the user add papers they already have (PDFs or arXiv links) later.
7. Trace every step, token and cost in the user's **self-hosted Langfuse**.

## Non-goals (for now)

- No implementation: the tool does not write, sketch or point at code for the
  user's own system. It stops at research and ideas.
- Not a general news digest; the community-signal stage (last30days: Reddit,
  HN, X) is dropped.
- No paper writing or LaTeX drafting.
- Fields outside embodied AI are not a design target; the breakdown assumes
  physical or simulated agents.

## Anti-goals (a failure even if it "works")

- Ideas that are already published, presented as novel. The critic exists to
  stop this.
- Shallow summaries that skip limitations; limitations and future work are
  where gaps come from.
- A run that silently re-reads and re-pays for papers already in the
  knowledge base.
- Unbounded agent loops with unpredictable cost.
- Anything hard-wired to one topic (WBC or otherwise).

## Constraints

- Same repo, branch `research-assistant`. Reuse `core/`:
  `llm.py` (Claude client, effort, fallbacks, cost), `tracing.py` (Langfuse),
  `obsidian.py`, `config.py`. Reuse the LaTeX/PDF extraction in
  `agents/arxiv_agent.py` (`extract_main_tex`, `clean_latex`,
  `_extract_pdf_text`) and arXiv search incl. `cat:` scoping.
- Langfuse: the self-hosted server on the robotics box
  (`LANGFUSE_HOST=http://192.168.50.68:3000`, project
  `multi-agent-research-tool`). Tracing must stay optional: if the server is
  unreachable the run continues (existing `core/tracing.py` behaviour).
- Output lands in the Obsidian vault (`vault_path` in `config.yaml`).
- Windows host, Python 3.12.
- **No Anthropic API key.** The user pays through their Claude plan, so every
  LLM call goes through the Claude Code CLI in headless mode
  (`claude -p --output-format json`), which uses the plan's login. Verified
  2026-10-24 with CLI 2.1.309: JSON output carries `result`, `is_error`,
  `usage` (input/output/cache tokens) and `total_cost_usd`.
  - `core/llm.py` keeps its interface but swaps the Anthropic SDK for a
    subprocess call to `claude -p`. Pass `--system-prompt` (replaces Claude
    Code's large default prompt, which otherwise inflates every call),
    `--tools ""` (agents get text in, text out; Python does all fetching),
    `--no-session-persistence`, `--model`, `--effort`.
  - Calls run sequentially or with low concurrency (config, default 2) to
    stay within plan rate limits; on a usage-limit error the run stops
    cleanly and keeps everything written so far (the next run resumes via
    the index).
  - Langfuse still records each call as a generation with token usage.
    `total_cost_usd` is an API-equivalent estimate, not a bill; label it so.
- **Lab context, used for relevance and feasibility:** robots are **Unitree
  G1** and **AgiBot X2** (either); simulator is **MuJoCo** by default but not
  fixed. The tool must not treat other simulators as irrelevant, only rank
  G1/X2 and MuJoCo-compatible work slightly higher and note sim portability in
  feasibility.

## Architecture (decided in conversation)

Five agents in a graph with **one bounded loop**:

```
            ┌──────────── targeted searches ◄───────────┐
            ▼                                            │
  arXiv Scout ─┐                                         │
               ├─► Reader ─► Knowledge base ─► Ideas ─► Critic ─► Report
 GitHub Scout ─┘
```

1. **arXiv Scout:** turns the topic into searches, finds candidate papers,
   ranks by relevance, skips anything already in the topic's knowledge base.
2. **GitHub Scout:** finds repos for the same topic: paper implementations,
   controllers/policies, simulators, benchmarks, datasets. Links repos to
   papers where possible. A hot idea with no released code is itself a gap
   signal.
3. **Reader:** for each new paper, reads the LaTeX source (PDF fallback) and
   writes the paper breakdown.
4. **Knowledge base** (storage, not an agent): paper notes, repo notes, gap map.
   Persists across runs, one per topic.
5. **Ideas:** reads the topic's whole knowledge base (not just this run) and
   proposes several ranked improvements / research directions.
6. **Critic:** for each idea, judges novelty (has this been done?) and
   feasibility. If novelty is unclear, it emits targeted queries and the
   scouts run again: that is the loop. Then the ideas are re-ranked.

### Paper breakdown (per paper)

1. Problem: one sentence.
2. Approach: method in plain words (RL / MPC / imitation / VLA / hybrid /
   learned model…) and the key idea.
3. Setup: embodiment (robot or agent, e.g. Unitree H1/G1, Franka arm, Digit),
   simulator (Isaac, MuJoCo…), sim only or real hardware, training cost.
4. Results: main numbers and baselines.
5. Limitations: stated *and* unstated (flat ground only, sim only, single
   robot…).
6. Future work the authors name.
7. Code & data: released code/models/datasets with links.
8. Key references: 3–5 papers it builds on.
9. Relevance: how it connects to improving methods in this topic, and an idea
   it sparks.

### Gap map

One table per topic across its papers: rows = approaches, columns =
capabilities, cells = papers that cover the combination. Empty cells are
candidate gaps. Rows and columns are derived from the papers (never
hard-coded) and updated as the knowledge base grows.

### Idea entry

Title, the improvement in plain words, which gap it fills (gap-map cell or
limitation it addresses, with citing papers), closest prior work, novelty
verdict (novel / partly done / done) with evidence, feasibility (sim-only vs
needs real robot, rough effort), rank.

## Builder's calls (made by the designer; the user can override)

- **Run mode: on demand**, `python pipeline.py "<topic>"`. The 8 AM scheduler
  is not used for this branch (kept in repo, not registered).
- **Plain Python orchestration**, no LangGraph: the graph is small (5 nodes,
  1 loop) and the existing code is plain Python.
- **Loop cap: 2 critic rounds** per run. **Paper cap: ~15 new papers per run**
  (config). Both in `config.yaml`.
- **Knowledge base layout** in the vault, one folder per topic slug:
  `Research/<topic-slug>/papers/<arxiv-id>.md`,
  `Research/<topic-slug>/repos/<owner>__<repo>.md`,
  `Research/<topic-slug>/gap-map.md`,
  `Research/<topic-slug>/ideas/YYYY-MM-DD.md`, plus a machine-readable
  `index.json` per topic (arXiv IDs and repos seen, for dedupe and for feeding
  the Ideas agent). A paper relevant to two topics gets a note in each.
- **Inbox for the user's own papers:** `Research/<topic-slug>/inbox/`. Drop PDFs
  or a `links.txt` of arXiv IDs/URLs; the next run on that topic reads them and
  moves them into the knowledge base.
- **Citation following** via the Semantic Scholar API (free, no key needed for
  low volume) to pull key references and "cited by" for the strongest papers.
- **GitHub** via the REST search API; optional `GITHUB_TOKEN` in `.env` for
  higher rate limits.
- **arXiv scoping:** default `cat:cs.RO OR cat:cs.LG OR cat:cs.AI OR cat:cs.CV`
  (embodied AI lives mostly in robotics and ML), configurable.
- **Models (via `claude -p --model`):** `claude-sonnet-5-5` at low effort for
  query generation and ranking; `claude-opus-5-5` for Reader, Ideas and
  Critic. Both configurable in `config.yaml`; `ANTHROPIC_API_KEY` is no longer
  used.
- **Ideas agent input stays bounded:** it reads a compact digest per paper
  (problem, approach, setup, limitations, future work, relevance) plus the gap
  map, not full notes, so a topic can grow to hundreds of papers.
- No default topic; the topic is always given on the command line.
- Old `agents/signal_agent.py`, `agents/synthesizer.py` and the last30days
  config are removed on this branch.

## Left to the builder

Prompt wording, ranking heuristics, exact Langfuse span names, how the gap map
table is merged across runs, topic-slug rules, test layout (keep the existing
no-network test style).

## Answered by the user (2026-10-24)

- Robots: Unitree G1 or AgiBot X2. Simulator: MuJoCo, but it can change.
- Budget: no API key; runs use the user's Claude plan through Claude Code.
  The per-run paper cap and loop cap are what keep a run within plan limits.

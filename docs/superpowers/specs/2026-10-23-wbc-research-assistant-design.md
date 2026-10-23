# WBC Research Assistant: design

Date: 2026-10-23 · Branch: `wbc-research-assistant`

## Intent

The user is joining a research lab and must find a paper they can write. The
paper comes out of **developing a whole-body controller (WBC) for humanoids and
making it better**. Plain WBC is well covered, so the value is in finding what
is *not* done yet, and in several concrete improvements rather than one "unique
thing". Stair climbing, push recovery and balancing are examples of directions,
not the scope.

They need to read far more papers than they can by hand. The tool reads the
literature and code for them, breaks each paper down well, keeps everything it
has learned between runs, and proposes ranked, novelty-checked research ideas.

This replaces the current daily "community buzz → brief" pipeline on this
branch. The old tool stays on `master`.

## Goals

1. Given a research topic (e.g. "humanoid whole-body control"), find the
   relevant papers (arXiv) and code (GitHub).
2. Break every paper down into a fixed, useful structure (below).
3. Accumulate a **knowledge base** that grows across runs; later runs build on
   earlier ones instead of starting over.
4. Maintain a **gap map** across all papers: approach × capability, so empty
   cells (unexplored combinations) are visible.
5. Propose **several ranked improvements/research ideas** for a WBC, each
   checked against the literature for "has this been done?" and feasibility.
6. Let the user add papers they already have (PDFs or arXiv links) later.
7. Trace every step, token and cost in the user's **self-hosted Langfuse**.

## Non-goals (for now)

- No controller code: the tool does not write, sketch or point at
  implementation of a WBC. It stops at research and ideas.
- Not a general news digest; the community-signal stage (last30days: Reddit,
  HN, X) is dropped.
- No paper writing or LaTeX drafting.

## Anti-goals (a failure even if it "works")

- Ideas that are already published, presented as novel. The critic exists to
  stop this.
- Shallow summaries that skip limitations; limitations and future work are
  where gaps come from.
- A run that silently re-reads and re-pays for papers already in the
  knowledge base.
- Unbounded agent loops with unpredictable cost.

## Constraints

- Same repo, new branch `wbc-research-assistant`. Reuse `core/`:
  `llm.py` (Claude client, effort, fallbacks, cost), `tracing.py` (Langfuse),
  `obsidian.py`, `config.py`. Reuse the LaTeX/PDF extraction in
  `agents/arxiv_agent.py` (`extract_main_tex`, `clean_latex`,
  `_extract_pdf_text`) and arXiv search incl. `cat:` scoping.
- Langfuse: the self-hosted server on the robotics box
  (`LANGFUSE_HOST=http://192.168.50.68:3000`, project
  `multi-agent-research-tool`). Tracing must stay optional: if the server is
  unreachable the run continues (existing `core/tracing.py` behaviour).
- Output lands in the Obsidian vault (`vault_path` in `config.yaml`).
- Windows host, Python 3.12, Anthropic API.

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
   ranks by relevance, skips anything already in the knowledge base.
2. **GitHub Scout:** finds repos for the same topic: paper implementations,
   controllers, simulators, benchmarks. Links repos to papers where possible.
   A hot idea with no released code is itself a gap signal.
3. **Reader:** for each new paper, reads the LaTeX source (PDF fallback) and
   writes the paper breakdown.
4. **Knowledge base** (storage, not an agent): paper notes, repo notes, gap map.
   Persists across runs.
5. **Ideas:** reads the whole knowledge base (not just this run) and proposes
   several ranked WBC improvements / research directions.
6. **Critic:** for each idea, judges novelty (has this been done?) and
   feasibility. If novelty is unclear, it emits targeted queries and the
   scouts run again: that is the loop. Then the ideas are re-ranked.

### Paper breakdown (per paper)

1. Problem: one sentence.
2. Approach: method in plain words (RL / MPC / hybrid / learned model…) and the
   key idea.
3. Setup: sim or real, robot (Unitree H1/G1, Atlas, Digit…), simulator
   (Isaac, MuJoCo…), training cost.
4. Results: main numbers and baselines.
5. Limitations: stated *and* unstated (flat ground only, sim only…).
6. Future work the authors name.
7. Code & data: released code/models/datasets with links.
8. Key references: 3–5 papers it builds on.
9. Relevance: how it connects to improving a WBC, and an idea it sparks.

### Gap map

One table across all papers: rows = approaches, columns = capabilities, cells
= papers that cover the combination. Empty cells are candidate gaps. Columns
are not hard-coded to stairs/push recovery; they are derived from the papers
and updated as the knowledge base grows.

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
- **Knowledge base layout** in the vault under `WBC Research/`:
  `papers/<arxiv-id>.md`, `repos/<owner>__<repo>.md`, `gap-map.md`,
  `ideas/YYYY-MM-DD.md`, plus a machine-readable `index.json` (arXiv IDs and
  repo names seen, for dedupe and for feeding the Ideas agent).
- **Inbox for the user's own papers:** `WBC Research/inbox/`. Drop PDFs or a
  `links.txt` of arXiv IDs/URLs; the next run reads them and moves them into
  the knowledge base.
- **Citation following** via the Semantic Scholar API (free, no key needed for
  low volume) to pull key references and "cited by" for the strongest papers.
- **GitHub** via the REST search API; optional `GITHUB_TOKEN` in `.env` for
  higher rate limits.
- **Models:** low effort for query generation and ranking; full model
  (`ANTHROPIC_MODEL`, default Opus 5.5) for Reader, Ideas and Critic.
- **Ideas agent input stays bounded:** it reads a compact digest per paper
  (problem, approach, setup, limitations, future work, relevance) plus the gap
  map, not full notes, so the knowledge base can grow to hundreds of papers.
- Topic default in `config.yaml`: "humanoid whole-body control".
- Old `agents/signal_agent.py`, `agents/synthesizer.py` and the last30days
  config are removed on this branch.

## Left to the builder

Prompt wording, ranking heuristics, exact Langfuse span names, how the gap map
table is merged across runs, test layout (keep the existing no-network test
style).

## Open questions for the user

- Which robot/simulator does the lab use? Used to rank relevance and judge
  feasibility (e.g. Unitree G1 in Isaac Lab).
- Rough spend you're comfortable with per run (a 15-paper run on Opus is
  likely a few dollars).

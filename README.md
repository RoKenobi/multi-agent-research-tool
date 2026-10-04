# Multi-Agent Research Tool

A "Signal-to-Substance" research pipeline that runs every morning and writes a structured intelligence brief directly into your Obsidian vault.

It finds what developers are actually talking about (not SEO blog spam), retrieves the real academic papers behind the buzz, and synthesizes both into a plain-English daily note — automatically.

---

## What It Does

Most AI research tools summarize tech blogs. This one goes where actual builders hang out.

**The pipeline runs 3 agents in sequence:**

```
Agent 1 — Signal        last30days-skill searches Reddit, HN, GitHub, X,
                        YouTube, and ArXiv for the last 30 days. Ranked
                        by upvotes, stars, and real engagement.
           ↓
Agent 2 — Substance     Extracts paper names from the signal, finds them
                        on ArXiv, and downloads the raw LaTeX source so
                        the math is preserved exactly as written.
           ↓
Agent 3 — Synthesizer   Claude reads both the community context and the
                        academic content and writes a structured brief
                        in plain English — no jargon without explanation.
           ↓
Output  — Obsidian      Saved as a .md file in your local vault under
                        Deep Signal / topic / YYYY-MM-DD.md
```

Every run is traced end-to-end in Langfuse so you can see exactly which step produced any result — useful when something looks wrong.

---

## Output Format

Each daily note has fixed sections:

- **TL;DR** — 2-3 sentences, readable in 10 seconds
- **What the Community is Saying** — why developers care, with callout blocks
- **The Papers** — plain-English breakdown of each paper's contribution
- **Key Formulas** — LaTeX equations with a plain-English explanation of each
- **What to Watch Next** — specific things to track in the next 2 weeks

---

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

The scheduler automatically uses `.venv` if it exists.

### 2. Clone the signal skill

```bash
cd skills
git clone https://github.com/mvanhorn/last30days-skill last30days
cd last30days
uv sync
cd ../..
```

> Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv) installed.

### 3. Configure secrets

```bash
cp .env.example .env
```

Fill in `.env`:

```env
# Required — from console.anthropic.com
ANTHROPIC_API_KEY=sk-ant-...
# Optional — defaults to claude-opus-5-5 (e.g. claude-sonnet-5-5 to cut cost)
ANTHROPIC_MODEL=

# Langfuse — free account at cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Optional — unlocks more signal sources
XAI_API_KEY=        # X / Twitter
GOOGLE_API_KEY=     # YouTube
BRAVE_API_KEY=      # General web search
```

### 4. Set your Obsidian vault path

Edit `config.yaml`:

```yaml
vault_path: "C:/Users/YourName/path/to/your/Obsidian/vault"
```

The pipeline stops with a clear error if this folder doesn't exist, so it never writes briefs into a phantom vault.

You can also edit the default research topics here:

```yaml
scheduled_topics:
  - "Physical AI"
  - "Embodied AI robotics"
  - "Vision Language Action models"
```

Other knobs in `config.yaml`:

| Key | Default | What it does |
|---|---|---|
| `max_papers` | `3` | Papers fetched per topic |
| `arxiv_category_filter` | `cat:cs.*` | Keeps short model names like "RT-2" from matching papers in other fields; `""` disables it |
| `paper_char_budget` | `20000` | Characters of each paper sent to the synthesizer (LaTeX preamble, comments and bibliography are stripped first) |
| `signal_char_budget` | `12000` | Characters of community signal sent to the synthesizer |

---

## Running

### On demand

```bash
python pipeline.py "Physical AI"
python pipeline.py "Multimodal LLMs"
```

### Scheduled daily at 8 AM (Windows)

Run once from an elevated command prompt:

```bash
scheduler\register.bat
```

To verify it's registered:

```bash
schtasks /query /tn "DeepSignalPipeline"
```

To trigger it manually right now:

```bash
schtasks /run /tn "DeepSignalPipeline"
```

Logs are written to `logs/pipeline.log`. If one topic fails, the remaining topics still run and the process exits with code 1 so Task Scheduler's "Last Run Result" shows it.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests cover the offline logic (LaTeX extraction, entity parsing, response handling, note writing, failure isolation); they make no network or LLM calls.

---

## Stack

| Layer | Tool |
|---|---|
| Signal discovery | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) |
| Academic papers | ArXiv API + LaTeX source download |
| LLM synthesis | Claude via the Anthropic API |
| Observability | [Langfuse](https://langfuse.com) |
| Output | Local Obsidian vault (.md files) |
| Scheduler | Windows Task Scheduler |

# Setup

## 1. Install Python dependencies
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Clone last30days-skill
```
cd skills
git clone https://github.com/mvanhorn/last30days-skill last30days
cd last30days
uv sync
cd ../..
```

## 3. Configure secrets
```
copy .env.example .env
```
Fill in your `.env`:
- `ANTHROPIC_API_KEY` — from console.anthropic.com (optionally `ANTHROPIC_MODEL`; defaults to `claude-opus-5-5`)
- `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` + `LANGFUSE_HOST` — from your self-hosted Langfuse (see "Self-hosting Langfuse" in the README), or from a free cloud.langfuse.com account with `LANGFUSE_HOST=https://cloud.langfuse.com`
- Optional: `XAI_API_KEY`, `GOOGLE_API_KEY`, `BRAVE_API_KEY` for richer signal

## 4. Set your Obsidian vault path in config.yaml
```yaml
vault_path: "C:/Users/YourName/path/to/Obsidian"
```

## 5. Test it
```
python pipeline.py "Physical AI"
```
Check your Obsidian vault under `Deep Signal/physical-ai/YYYY-MM-DD.md`

## 6. Register the daily 8 AM scheduler (run as admin)
```
scheduler\register.bat
```

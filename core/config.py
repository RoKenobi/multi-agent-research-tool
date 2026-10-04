import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent


def load_env() -> None:
    load_dotenv(ROOT / ".env")
    os.environ.setdefault("AWS_REGION", "us-east-1")


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_root"] = ROOT
    cfg["_vault"] = Path(cfg["vault_path"]).expanduser()
    # Fail before spending API calls, and never mkdir a phantom vault on a typo
    # (or before OneDrive has mounted).
    if not cfg["_vault"].is_dir():
        raise SystemExit(f"vault_path does not exist: {cfg['_vault']} — fix it in config.yaml")
    return cfg

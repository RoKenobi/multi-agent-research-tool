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
    cfg["_vault"] = Path(cfg["vault_path"])
    return cfg

# -*- coding: utf-8 -*-
"""配置与路径。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
SEED_DIR = ROOT / "server" / "seed"
DB_PATH = DATA_DIR / "app.db"


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass


_load_env()

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat").strip()
QW_KEY = os.getenv("QWEATHER_KEY", "").strip()
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "45"))

_MODE = os.getenv("MOCK_MODE", "auto").strip().lower()


def use_mock() -> bool:
    if _MODE in ("1", "true", "yes", "on"):
        return True
    if _MODE in ("0", "false", "no", "off"):
        return False
    return not bool(LLM_API_KEY)


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

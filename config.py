"""Kuku Tag Bot - config (reads Railway Variables)."""
import os


def _req(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise SystemExit(f"❌ Missing environment variable: {key}")
    return val


API_ID = int(_req("API_ID"))
API_HASH = _req("API_HASH")
BOT_TOKEN = _req("BOT_TOKEN")
OWNER_ID = int(_req("OWNER_ID"))
MONGO_URL = _req("MONGO_URL")
DB_NAME = os.getenv("DB_NAME", "kukudb")
SESSION = "kuku"

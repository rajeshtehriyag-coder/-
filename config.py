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
MONGO_URL = (
    os.getenv("MONGO_URL")
    or os.getenv("MONGO_DB_URI")
    or os.getenv("MONGODB_URL")
    or os.getenv("MONGO_URI")
)
if not MONGO_URL:
    raise SystemExit("❌ Missing environment variable: MONGO_URL")
DB_NAME = os.getenv("DB_NAME", "kukudb")
SESSION = "kuku"

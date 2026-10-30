"""⚡ 𝕂𝕦𝕜𝕦 Tag Bot - entry point."""
import logging

from pyrogram import Client

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

app = Client(
    config.SESSION,
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    plugins=dict(root="plugins"),
    in_memory=True,
)

if __name__ == "__main__":
    logging.info("⚡ Kuku Tag Bot starting...")
    app.run()

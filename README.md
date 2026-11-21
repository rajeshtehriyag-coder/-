# ⚡ Kuku Tag Bot v3

Premium Telegram tagging bot built with Aiogram 3 and MongoDB, ready for Railway.

## Features
- Tagging: /all, /admins, /anybody, /gmtag, /gntag, /vctag, /tagall, /stop
- Plain triggers: all, @all, @admin
- Group settings menu: tag style, per message, limit, font, theme, access
- Welcome and left messages, owner and sudo tools
- Exact-copy broadcast: /broadcast, /gcast, /ucast
- Clone system: users can connect their own bot with /clone
- Master panel to manage all clones

## Environment variables
Required:
- BOT_TOKEN
- OWNER_ID
- MONGO_DB_URI
- DATABASE_NAME
- ENCRYPTION_KEY

Optional:
- SUDO_IDS
- TIMEZONE
- LOG_GROUP_ID
- MAX_CLONES_PER_USER

## Deploy on Railway
1. Upload these files to a GitHub repo.
2. Create a Railway project from the repo.
3. Add the variables above.
4. Start command: python main.py

## Notes
- Disable privacy in BotFather (/setprivacy) so the bot can read group messages.
- Make the bot admin in your group.
- Never share your tokens, MongoDB password or ENCRYPTION_KEY.

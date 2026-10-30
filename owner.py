"""Owner only: /broadcast /stats /ban /unban"""
import asyncio
import time

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

import database as db
from config import OWNER_ID
from fonts import S, wrap

HTML = ParseMode.HTML
OWN = filters.user(OWNER_ID)
START = time.time()


@Client.on_message(filters.command("stats") & OWN)
async def stats_cmd(c, m):
    from plugins.tagging import RUN

    s = await db.stats()
    up = int(time.time() - START)
    d, r = divmod(up, 86400)
    h, r = divmod(r, 3600)
    body = (
        f"👤 {S('users')}  ›  <b>{s['users']}</b>\n"
        f"👥 {S('groups')}  ›  <b>{s['groups']}</b>\n"
        f"🚫 {S('banned')}  ›  <b>{s['bans']}</b>\n"
        f"🏷 {S('active tagging')}  ›  <b>{len(RUN)}</b>\n"
        f"⏱ {S('uptime')}  ›  <b>{d}d {h}h {r // 60}m</b>"
    )
    await m.reply_text(wrap("neon", S("bot stats"), body), parse_mode=HTML)


@Client.on_message(filters.command("broadcast") & OWN)
async def broadcast(c, m):
    reply = m.reply_to_message
    parts = m.text.split(None, 1)
    text = parts[1] if len(parts) > 1 else None
    if not reply and not text:
        return await m.reply_text("Usage: <code>/broadcast your message</code> (ya kisi message par reply karo)", parse_mode=HTML)
    targets = await db.all_targets()
    note = await m.reply_text(f"📣 Broadcast shuru... {len(targets)} chats")
    ok = fail = 0
    for cid in targets:
        for _ in range(2):
            try:
                if reply:
                    await reply.copy(cid)
                else:
                    await c.send_message(cid, text)
                ok += 1
                break
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception:
                fail += 1
                break
        await asyncio.sleep(0.1)
    await note.edit_text(f"✅ Broadcast done\n\n📬 Sent: {ok}\n❌ Failed: {fail}")


async def _id_arg(m):
    parts = m.text.split()
    if len(parts) < 2:
        await m.reply_text("Usage: <code>/ban user_or_group_id</code>", parse_mode=HTML)
        return None
    try:
        return int(parts[1])
    except ValueError:
        await m.reply_text("❌ ID number honi chahiye.")
        return None


@Client.on_message(filters.command("ban") & OWN)
async def ban_cmd(c, m):
    i = await _id_arg(m)
    if i is not None:
        await db.ban(i)
        await m.reply_text(f"🚫 Banned: <code>{i}</code>", parse_mode=HTML)


@Client.on_message(filters.command("unban") & OWN)
async def unban_cmd(c, m):
    i = await _id_arg(m)
    if i is not None:
        await db.unban(i)
        await m.reply_text(f"✅ Unbanned: <code>{i}</code>", parse_mode=HTML)

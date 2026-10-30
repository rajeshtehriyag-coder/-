"""Welcome (group DP + name + user details) and Left message."""
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

import database as db
from fonts import S, wrap
from utils import log

import asyncio
import html

HTML = ParseMode.HTML


async def group_photo(client, chat_id):
    try:
        chat = await client.get_chat(chat_id)
        if chat.photo:
            return await client.download_media(chat.photo.big_file_id, in_memory=True)
    except Exception as e:
        log.info("no group photo: %s", e)
    return None


def link(u) -> str:
    return f'<a href="tg://user?id={u.id}">{html.escape(u.first_name or "User")}</a>'


@Client.on_message(filters.group & filters.new_chat_members, group=2)
async def welcome(client, message):
    chat = message.chat
    cfg = await db.get_chat(chat.id)
    title = html.escape(chat.title or "Group")
    for u in message.new_chat_members:
        try:
            if u.is_self:
                await db.add_group(chat.id, chat.title or "")
                await client.send_message(
                    chat.id,
                    wrap("neon", S("thanks for adding me"),
                         f"⚡ <b>{S('kuku tag bot')}</b> {S('is ready')}!\n\n"
                         f"🛡 {S('make me admin to tag everyone')}\n⚙️ /settings  •  📖 /start"),
                    parse_mode=HTML,
                )
                continue
            if u.is_bot or not cfg["welcome"]:
                continue
            try:
                count = await client.get_chat_members_count(chat.id)
            except Exception:
                count = "?"
            body = (
                f"👤 {S('name')}  ›  {link(u)}\n"
                f"🆔 {S('id')}  ›  <code>{u.id}</code>\n"
                f"🔗 {S('username')}  ›  {'@' + u.username if u.username else S('none')}\n"
                f"🏠 {S('group')}  ›  <b>{title}</b>\n"
                f"👥 {S('members')}  ›  <b>{count}</b>"
            )
            caption = wrap("neon", S("welcome"), body)
            photo = await group_photo(client, chat.id)
            if photo:
                photo.seek(0)
                await client.send_photo(chat.id, photo, caption=caption, parse_mode=HTML)
            else:
                await client.send_message(chat.id, caption, parse_mode=HTML)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            log.warning("welcome error: %s", e)


@Client.on_message(filters.group & filters.left_chat_member, group=2)
async def left(client, message):
    u = message.left_chat_member
    if not u or u.is_self or u.is_bot:
        return
    cfg = await db.get_chat(message.chat.id)
    if not cfg["left"]:
        return
    text = wrap("neon", S("goodbye"), f"👋 {link(u)} {S('left the group')} 😢\n💔 {S('bye bye, take care')} ✨")
    try:
        await client.send_message(message.chat.id, text, parse_mode=HTML)
    except Exception as e:
        log.warning("left msg error: %s", e)

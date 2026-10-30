"""Shared helpers: permissions, member fetching, mentions, text parsing."""
import html
import logging
import random
import re

from pyrogram.enums import ChatMemberStatus, ChatMembersFilter, UserStatus

import database as db
from config import OWNER_ID

log = logging.getLogger("kuku")

EMOJIS = list("😀😎🥳🤩😍🔥⚡💫✨🌸🍀🦋🌈💎👑🎯🚀🎉💖🌟🍕🎧🐱🦁🐯🦄🌙☀️🍭")
_me = None


async def get_me(client):
    global _me
    if _me is None:
        _me = await client.get_me()
    return _me


async def is_admin(client, chat_id: int, uid: int) -> bool:
    if uid == OWNER_ID:
        return True
    try:
        m = await client.get_chat_member(chat_id, uid)
    except Exception:
        return False
    return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


async def can_use(client, message, level: str) -> bool:
    """level: all | staff | owner | botowner"""
    uid = message.from_user.id if message.from_user else None
    if uid == OWNER_ID:
        return True
    if level == "all":
        return True
    # anonymous admin posting as the group
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return level == "staff"
    if uid is None or level == "botowner":
        return False
    try:
        m = await client.get_chat_member(message.chat.id, uid)
    except Exception:
        return False
    if level == "owner":
        return m.status == ChatMemberStatus.OWNER
    return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


async def fetch_members(client, chat_id: int, admins_only: bool = False) -> list:
    out = []
    kwargs = {"filter": ChatMembersFilter.ADMINISTRATORS} if admins_only else {}
    try:
        async for m in client.get_chat_members(chat_id, **kwargs):
            u = m.user
            if not u or u.is_bot or u.is_deleted:
                continue
            out.append(u)
    except Exception as e:
        log.warning("fetch_members failed: %s", e)
    return out


_RANK = {
    UserStatus.ONLINE: 0,
    UserStatus.RECENTLY: 1,
    UserStatus.LAST_WEEK: 2,
    UserStatus.LAST_MONTH: 3,
    UserStatus.LONG_AGO: 4,
}


def status_rank(user) -> int:
    return _RANK.get(user.status, 5)


def mention(u, style: str) -> str:
    name = html.escape((u.first_name or "User")[:25])
    if style == "emoji":
        return f'<a href="tg://user?id={u.id}">{random.choice(EMOJIS)}</a>'
    if style == "username" and u.username:
        return f"@{u.username}"
    if style == "plain":
        return f"<b>{name}</b>"
    return f'<a href="tg://user?id={u.id}">{name}</a>'


_PREFIX = re.compile(r"(?is)^\s*(/\w+(@\w+)?|@all|all|@admins?)(\s+|$)")


def extract_text(message) -> str:
    """Text after the command, as HTML (keeps premium emoji + formatting)."""
    src = message.text or message.caption
    if not src:
        return ""
    return _PREFIX.sub("", src.html, count=1).strip()


async def banned(message) -> bool:
    if await db.is_banned(message.chat.id):
        return True
    return bool(message.from_user and await db.is_banned(message.from_user.id))

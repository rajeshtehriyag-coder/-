"""
⚡ KUKU TAG BOT v3 — Aiogram 3 · MongoDB · Clone system · Exact-copy broadcast (single file)

ENV: BOT_TOKEN, OWNER_ID, MONGO_DB_URI, DATABASE_NAME, ENCRYPTION_KEY   (required)
     SUDO_IDS, TIMEZONE, LOG_GROUP_ID, MAX_CLONES_PER_USER, BOT_USERNAME  (optional)
"""
import asyncio
import base64
import contextlib
import hashlib
import html
import logging
import os
import random
import re
import sys
import time
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.exceptions import (
    TelegramAPIError, TelegramBadRequest, TelegramForbiddenError,
    TelegramRetryAfter, TelegramUnauthorizedError,
)
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import (
    BotCommand, BotCommandScopeChat, BotCommandScopeDefault, BufferedInputFile,
    CallbackQuery, ChatMemberUpdated, ErrorEvent, InlineKeyboardButton,
    InlineKeyboardMarkup, Message,
)
from cryptography.fernet import Fernet, InvalidToken
from motor.motor_asyncio import AsyncIOMotorClient

# ═══════════════════════════ CONFIG ═══════════════════════════
def env(*names, default=None, required=False):
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    if required:
        raise SystemExit(f"❌ Missing environment variable: {names[0]}")
    return default


BOT_TOKEN = env("BOT_TOKEN", required=True)
OWNER_ID = int(env("OWNER_ID", required=True))
MONGO_URI = env("MONGO_DB_URI", "MONGO_URL", "MONGODB_URL", "MONGO_URI", required=True)
DB_NAME = env("DATABASE_NAME", "DB_NAME", default="kukuv3")
ENC_KEY = env("ENCRYPTION_KEY", required=True)
TZ = ZoneInfo(env("TIMEZONE", default="Asia/Kolkata"))
LOG_GROUP_ID = int(env("LOG_GROUP_ID", default="0"))
MAX_CLONES = int(env("MAX_CLONES_PER_USER", default="3"))
SUDO = {int(x) for x in re.findall(r"-?\d+", env("SUDO_IDS", default=""))}

try:
    FERNET = Fernet(ENC_KEY.encode())
except Exception:  # any long random string works
    FERNET = Fernet(base64.urlsafe_b64encode(hashlib.sha256(ENC_KEY.encode()).digest()))

_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")


class Redact(logging.Filter):
    """Tokens must never reach the logs."""
    def filter(self, record):
        record.msg = _TOKEN_RE.sub("[token]", record.getMessage())
        record.args = ()
        return True


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
for _h in logging.getLogger().handlers:
    _h.addFilter(Redact())
log = logging.getLogger("kuku")

HTML = ParseMode.HTML
DEFAULT = DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True)
GROUPS = {ChatType.GROUP, ChatType.SUPERGROUP}
GROUP_F = F.chat.type.in_({"group", "supergroup"})
PRIVATE_F = F.chat.type == "private"
START_TIME = time.time()
MASTER: Bot = None
MASTER_UN = ""
CTX = {}   # bot_id -> {"master": bool, "owner_id": int, "username": str}
RT = {}    # clone bot_id -> {"bot", "dp", "task"}
RUN = {}   # (bot_id, chat_id) -> tagging state
BC = {}    # bot_id -> broadcast state
ALBUMS = OrderedDict()  # (chat_id, media_group_id) -> [message_ids]


def now_str():
    return datetime.now(TZ).strftime("%d %b %Y, %I:%M %p")


def esc(s):
    return html.escape(str(s or ""))


def ulink(u):
    return f'<a href="tg://user?id={u.id}">{esc(u.first_name or "User")}</a>'


# ═══════════════════════════ FONTS & THEMES ═══════════════════════════
FONT_NAMES = {"normal": "Normal", "bold": "𝗕𝗼𝗹𝗱", "italic": "𝙄𝙩𝙖𝙡𝙞𝙘", "script": "𝓢𝓬𝓻𝓲𝓹𝓽", "small": "ꜱᴍᴀʟʟ ᴄᴀᴘꜱ", "double": "𝔻𝕠𝕦𝕓𝕝𝕖"}
THEME_NAMES = {"neon": "💠 Neon", "premium": "👑 Premium", "dark": "🌑 Dark Box", "minimal": "▫️ Minimal", "default": "✨ Default"}
BULLET = {"neon": "💠", "premium": "✦", "dark": "▸", "minimal": "•", "default": "•"}


def _mk(up, lo, exc=None):
    m = {}
    for i in range(26):
        m[chr(65 + i)] = chr(up + i)
        m[chr(97 + i)] = chr(lo + i)
    if exc:
        m.update(exc)
    return m


_SMALL = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ"
_SM = {}
for _i, _c in enumerate(_SMALL):
    _SM[chr(97 + _i)] = _c
    _SM[chr(65 + _i)] = _c
_MAPS = {
    "bold": _mk(0x1D5D4, 0x1D5EE), "italic": _mk(0x1D63C, 0x1D656), "script": _mk(0x1D4D0, 0x1D4EA),
    "double": _mk(0x1D538, 0x1D552, {"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"}),
    "small": _SM,
}
_TABLES = {k: str.maketrans(v) for k, v in _MAPS.items()}
_TOKEN = re.compile(r"(<[^>]*>|&#?\w+;)")
_SKIP = {"a", "code", "pre", "tg-emoji"}
_TAGN = re.compile(r"<(/?)([\w-]+)")


def f(text, font):
    t = _TABLES.get(font)
    return text.translate(t) if t else text


def f_html(h, font):
    """Font only on normal text: links, code and premium emoji stay untouched."""
    t = _TABLES.get(font)
    if not t:
        return h
    out, skip = [], 0
    for i, p in enumerate(_TOKEN.split(h)):
        if i % 2:
            mm = _TAGN.match(p)
            if mm and mm.group(2).lower() in _SKIP:
                skip = max(skip + (-1 if mm.group(1) else 1), 0)
            out.append(p)
        else:
            out.append(p if skip else p.translate(t))
    return "".join(out)


def S(text):
    return text.translate(_TABLES["small"])


def wrap(theme, title, body):
    if theme == "neon":
        bar = "▰▱" * 7
        return f"<b>⚡ ⟦ {title} ⟧ ⚡</b>\n<b>{bar}</b>\n\n{body}\n\n<b>{bar}</b>\n💠 <i>{S('kuku tag bot')}</i> 💠"
    if theme == "premium":
        return f"✦ ━━━━ ✦ <b>{title}</b> ✦ ━━━━ ✦\n\n{body}\n\n✦ ━━━━━━━━━━━━━━ ✦"
    if theme == "dark":
        return f"<blockquote><b>{title}</b>\n\n{body}</blockquote>"
    if theme == "minimal":
        return f"<b>{title}</b>\n{body}"
    return f"✨ <b>{title}</b> ✨\n\n{body}"


# ═══════════════════════════ DATABASE ═══════════════════════════
db = None
DEFAULTS = dict(style="mention", per=5, limit=0, font="bold", theme="neon", who_all="staff", who_tagall="staff", welcome=True, left=True)
_cfg, _bans, _sup = {}, {}, {}
_seen_groups, _mseen, _pcache, _gphoto, _role, _admsync = set(), {}, {}, {}, {}, {}


async def init_db():
    global db
    db = AsyncIOMotorClient(MONGO_URI)[DB_NAME]
    idx = [
        (db.users, [("bot_id", 1), ("user_id", 1)], True), (db.groups, [("bot_id", 1), ("chat_id", 1)], True),
        (db.members, [("bot_id", 1), ("chat_id", 1), ("user_id", 1)], True), (db.settings, [("bot_id", 1), ("chat_id", 1)], True),
        (db.banned_users, [("bot_id", 1), ("target_id", 1)], True), (db.support_links, [("bot_id", 1), ("key", 1)], True),
        (db.admins, [("bot_id", 1), ("chat_id", 1)], True), (db.sudo, [("user_id", 1)], True),
        (db.clones, [("bot_id", 1)], True), (db.clones, [("token_hash", 1)], True),
        (db.broadcast_logs, [("bot_id", 1), ("time", -1)], False), (db.tag_sessions, [("bot_id", 1), ("chat_id", 1)], False),
    ]
    for col, keys, uniq in idx:
        try:
            await col.create_index(keys, unique=uniq)
        except Exception as e:
            log.warning("index skipped: %s", e)
    SUDO.update([d["user_id"] async for d in db.sudo.find()])


async def get_cfg(bid, cid):
    k = (bid, cid)
    if k in _cfg:
        return _cfg[k]
    d = await db.settings.find_one({"bot_id": bid, "chat_id": cid}) or {}
    _cfg[k] = {**DEFAULTS, **{a: b for a, b in d.items() if a in DEFAULTS}}
    return _cfg[k]


async def set_cfg(bid, cid, key, val):
    (await get_cfg(bid, cid))[key] = val
    await db.settings.update_one({"bot_id": bid, "chat_id": cid}, {"$set": {key: val}}, upsert=True)


async def reg_user(bid, u):
    r = await db.users.update_one(
        {"bot_id": bid, "user_id": u.id},
        {"$set": {"name": u.full_name, "username": u.username, "blocked": False}, "$setOnInsert": {"opt_in": True, "joined": now_str()}},
        upsert=True)
    return r.upserted_id is not None


async def reg_group(bid, chat):
    k = (bid, chat.id)
    if k in _seen_groups:
        return False
    _seen_groups.add(k)
    r = await db.groups.update_one(
        {"bot_id": bid, "chat_id": chat.id},
        {"$set": {"title": chat.title or "", "username": chat.username, "active": True}, "$setOnInsert": {"joined": now_str()}},
        upsert=True)
    return r.upserted_id is not None


async def track_member(bid, cid, u, force=False):
    if u.is_bot:
        return
    k, t = (bid, cid, u.id), time.time()
    if not force and t - _mseen.get(k, 0) < 900:
        return
    if len(_mseen) > 60000:
        _mseen.clear()
    _mseen[k] = t
    await db.members.update_one(
        {"bot_id": bid, "chat_id": cid, "user_id": u.id},
        {"$set": {"name": u.first_name or "User", "username": u.username, "last_seen": t, "left": False}}, upsert=True)


async def db_members(bid, cid):
    q = {"bot_id": bid, "chat_id": cid, "left": {"$ne": True}, "opt_out": {"$ne": True}}
    return [{"id": d["user_id"], "name": d.get("name"), "username": d.get("username")}
            async for d in db.members.find(q).sort("last_seen", -1)]


async def is_banned(bid, tid):
    if bid not in _bans:
        _bans[bid] = {d["target_id"] async for d in db.banned_users.find({"bot_id": bid})}
    return tid in _bans[bid]


async def get_meta_links(bid):
    hit = _sup.get(bid)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    links = {d["key"]: d async for d in db.support_links.find({"bot_id": bid})}
    _sup[bid] = (time.time(), links)
    return links


# ═══════════════════════════ PERMISSIONS ═══════════════════════════
def is_owner(bot, uid):
    c = CTX.get(bot.id)
    return bool(c) and (uid == OWNER_ID or uid == c["owner_id"] or (c["master"] and uid in SUDO))


def is_master(bot):
    return bool(CTX.get(bot.id, {}).get("master"))


class BotOwner(BaseFilter):
    async def __call__(self, message: Message, bot: Bot) -> bool:
        return bool(message.from_user) and is_owner(bot, message.from_user.id)


class MasterSudo(BaseFilter):
    async def __call__(self, message: Message, bot: Bot) -> bool:
        return is_master(bot) and bool(message.from_user) and (message.from_user.id == OWNER_ID or message.from_user.id in SUDO)


class MasterOwner(BaseFilter):
    async def __call__(self, message: Message, bot: Bot) -> bool:
        return is_master(bot) and bool(message.from_user) and message.from_user.id == OWNER_ID


class MasterAny(BaseFilter):
    async def __call__(self, message: Message, bot: Bot) -> bool:
        return is_master(bot)


async def chat_role(bot, cid, uid):
    k = (bot.id, cid, uid)
    hit = _role.get(k)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    role = None
    try:
        m = await bot.get_chat_member(cid, uid)
        role = "owner" if m.status == ChatMemberStatus.CREATOR else "admin" if m.status == ChatMemberStatus.ADMINISTRATOR else None
    except TelegramAPIError:
        pass
    if len(_role) > 5000:
        _role.clear()
    _role[k] = (time.time(), role)
    return role


async def is_admin(bot, cid, uid):
    return is_owner(bot, uid) or (await chat_role(bot, cid, uid)) is not None


async def can_use(bot, message, level):
    uid = message.from_user.id if message.from_user else None
    if uid is not None and is_owner(bot, uid):
        return True
    if level == "all":
        return True
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return level == "staff"
    if uid is None or level == "botowner":
        return False
    role = await chat_role(bot, message.chat.id, uid)
    return role == "owner" if level == "owner" else role is not None


# ═══════════════════════════ HELPERS ═══════════════════════════
def B(text, data=None, url=None):
    return InlineKeyboardButton(text=text, callback_data=data, url=url)


def K(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def clone_url():
    return f"https://t.me/{MASTER_UN}?start=clone"


def clone_kb():
    return K([[B("🤖 Create Your Own Bot (Clone)", url=clone_url())]])


_PREFIX = re.compile(r"(?is)^\s*(/\w+(@\w+)?|@all|all|@admins?)(\s+|$)")


def strip_cmd(h):
    return _PREFIX.sub("", h or "", count=1).strip()


async def send_log(text):
    if LOG_GROUP_ID and MASTER:
        with contextlib.suppress(Exception):
            await MASTER.send_message(LOG_GROUP_ID, text)


def norm_url(s):
    s = s.strip()
    if s.startswith("@") and len(s) > 1:
        return "https://t.me/" + s[1:]
    if s.isdigit():
        return f"tg://user?id={s}"
    if s.startswith(("http://", "https://", "tg://")):
        return s
    if s.startswith(("t.me/", "telegram.me/")):
        return "https://" + s
    return None


def split_link_name(tokens):
    """Accepts '[link] [name]' or '[name] [link]'."""
    idx = next((i for i, t in enumerate(tokens) if t.startswith(("http://", "https://", "tg://", "@", "t.me/", "telegram.me/"))), None)
    if idx is None and tokens and tokens[-1].isdigit():
        idx = len(tokens) - 1
    if idx is None:
        return None, None
    url = norm_url(tokens[idx])
    name = " ".join(tokens[:idx] + tokens[idx + 1:]).strip()
    return url, name


async def user_photo_id(bot, uid):
    k = (bot.id, uid)
    if k in _pcache:
        return _pcache[k]
    try:
        ph = await bot.get_user_profile_photos(uid, limit=1)
        fid = ph.photos[0][-1].file_id if ph.total_count else ""
        _pcache[k] = fid
        return fid
    except TelegramAPIError:
        return ""


async def group_photo(bot, cid):
    k = (bot.id, cid)
    hit = _gphoto.get(k)
    if hit and time.time() - hit[0] < 900:
        return hit[1]
    data = None
    try:
        chat = await bot.get_chat(cid)
        if chat.photo:
            buf = await bot.download(chat.photo.big_file_id)
            data = buf.read()
    except Exception as e:
        log.info("no group photo: %s", e)
    _gphoto[k] = (time.time(), data)
    return data


# ═══════════════════════════ REGISTRY (one Router per bot) ═══════════════════════════
_REG = []


def on(event, *flt):
    def deco(fn):
        _REG.append((event, flt, fn))
        return fn
    return deco


class Guard:
    """Outer middleware: tracks members, drops banned users, caches albums."""
    async def __call__(self, handler, event, data):
        bot = data["bot"]
        c = CTX.get(bot.id)
        if not c or not isinstance(event, Message):
            return await handler(event, data) if c else None
        u = event.from_user
        try:
            if event.chat.type in GROUPS and u:
                await track_member(bot.id, event.chat.id, u)
            if u and not is_owner(bot, u.id):
                if await is_banned(bot.id, u.id) or (event.chat.type != ChatType.PRIVATE and await is_banned(bot.id, event.chat.id)):
                    return None
            if event.chat.type == ChatType.PRIVATE and event.media_group_id and u and is_owner(bot, u.id):
                key = (event.chat.id, event.media_group_id)
                ALBUMS.setdefault(key, []).append(event.message_id)
                while len(ALBUMS) > 200:
                    ALBUMS.popitem(last=False)
        except Exception as e:
            log.warning("guard error: %s", e)
        return await handler(event, data)


async def on_error(event: ErrorEvent):
    log.error("handler error: %s", event.exception, exc_info=event.exception)
    return True


def build_dispatcher():
    dp, r = Dispatcher(), Router()
    mw = Guard()
    r.message.outer_middleware(mw)
    for ev, flt, fn in _REG:
        getattr(r, ev).register(fn, *flt)
    dp.include_router(r)
    dp.errors.register(on_error)
    return dp


# ═══════════════════════════ START / HELP / OPT-OUT ═══════════════════════════
def home_caption(u):
    body = (f"👋 {S('hello')} {ulink(u)}\n🆔 {S('id')}  ›  <code>{u.id}</code>\n\n"
            f"✨ <b>{S('premium tagging bot for telegram')}</b>\n💠 {S('tag everyone in style')}\n"
            f"💠 {S('fonts, themes and emoji styles')}\n💠 {S('welcome with group dp')}\n\n"
            f"🛡 {S('add me to your group and make me admin')}")
    return wrap("neon", S("kuku"), body)


async def home_markup(bot):
    uname = CTX[bot.id]["username"]
    links = await get_meta_links(bot.id)
    rows = [[B("➕ Add Me To Group", url=f"https://t.me/{uname}?startgroup=true&admin=invite_users+delete_messages")]]
    own = links.get("owner") or {"url": f"tg://user?id={CTX[bot.id]['owner_id']}", "name": "👑 Owner"}
    rows.append([B("📖 Guide", "hp:help"), B(own["name"], url=own["url"])])
    rows.append([B("🤖 Create Your Own Bot (Clone)", url=clone_url())])
    sup = [B(v["name"], url=v["url"]) for k, v in sorted(links.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0) if k != "owner"]
    rows += [sup[i:i + 2] for i in range(0, len(sup), 2)]
    return K(rows)


async def send_home(bot, chat_id, user):
    cap = home_caption(user)
    kb = await home_markup(bot)
    fid = await user_photo_id(bot, user.id)
    if fid:
        try:
            return await bot.send_photo(chat_id, fid, caption=cap, reply_markup=kb)
        except TelegramAPIError as e:
            log.warning("home photo failed: %s", e)
            _pcache.pop((bot.id, user.id), None)
    await bot.send_message(chat_id, cap, reply_markup=kb)


def help_text(bot, uid):
    t = ("🏷 <b>Tagging</b> <i>(admins)</i>\n• /all [text] • all • @all\n• /admins [text] • @admin\n• /anybody • /gmtag • /gntag • /vctag\n"
         "• /tagall [text] — one by one fun tag\n• /stop — stop tagging\n\n⚙️ <b>Group</b>\n• /settings • /unreg • /reg • /id\n\n"
         "🔕 <b>Privacy</b>\n• /optout • /optin (DM broadcast)")
    if is_master(bot):
        t += "\n\n🤖 <b>Clone</b>\n• /clone [token] • /myclones\n• /stopclone • /startclone • /deleteclone"
    if is_owner(bot, uid):
        t += ("\n\n👑 <b>Owner</b>\n• /stats • /broadcast • /gcast • /bclog\n• /ban • /unban • /groups • /ping\n"
              "• /setsupport [n] • /delsupport n • /supports • /setowner")
    if is_master(bot) and (uid == OWNER_ID or uid in SUDO):
        t += "\n\n🛡 <b>Master</b>\n• /ucast • /clonelist\n• /disableclone • /enableclone • /delclone"
    if uid == OWNER_ID and is_master(bot):
        t += "\n• /addsudo • /delsudo • /sudolist • /restart"
    return wrap("neon", S("guide"), t)


async def _log_new_user(bot, u):
    total = await db.users.count_documents({"bot_id": bot.id})
    via = "" if is_master(bot) else f"\n• Via clone: @{CTX[bot.id]['username']}"
    await send_log(f"👤 <b>New User Started Bot</b>\n\n• Name: {ulink(u)}\n• Username: {'@' + u.username if u.username else 'None'}\n"
                   f"• ID: <code>{u.id}</code>\n• Time: {now_str()}\n• Total users: <b>{total}</b>{via}")


CLONE_GUIDE = ("🤖 <b>Apna khud ka Tag Bot banao (Clone)</b>\n\n1. @BotFather me <code>/newbot</code> se naya bot banao\n"
               "2. Uska token yaha bhejo: <code>/clone TOKEN</code>\n3. @BotFather me <code>/setprivacy</code> → Disable karo\n"
               "4. Apne bot ko group me admin banao\n\n🔒 Token turant delete hoke encrypted save hota hai.\n"
               "Control: /myclones /stopclone /startclone /deleteclone")


@on("message", Command("start"))
async def start_cmd(message: Message, bot: Bot, command: CommandObject):
    u = message.from_user
    if not u:
        return
    if message.chat.type == ChatType.PRIVATE:
        isnew = await reg_user(bot.id, u)
        if command.args == "clone" and is_master(bot):
            await message.answer(CLONE_GUIDE)
        else:
            await send_home(bot, message.chat.id, u)
        if isnew:
            asyncio.create_task(_log_new_user(bot, u))
    else:
        await reg_group(bot.id, message.chat)
        await message.answer(home_caption(u), reply_markup=await home_markup(bot))


@on("message", Command("help"))
async def help_cmd(message: Message, bot: Bot):
    await message.answer(help_text(bot, message.from_user.id if message.from_user else 0))


@on("callback_query", F.data.startswith("hp:"))
async def help_cb(q: CallbackQuery, bot: Bot):
    msg = q.message
    if q.data == "hp:help":
        text = help_text(bot, q.from_user.id)
        kb = K([[B("⬅️ Back", "hp:back")]])
        with contextlib.suppress(TelegramBadRequest):
            if msg.photo and len(text) <= 1000:
                await msg.edit_caption(caption=text, reply_markup=kb)
            elif msg.photo:
                await msg.delete()
                await bot.send_message(msg.chat.id, text, reply_markup=kb)
            else:
                await msg.edit_text(text, reply_markup=kb)
    else:
        with contextlib.suppress(TelegramAPIError):
            await msg.delete()
        await send_home(bot, msg.chat.id, q.from_user)
    await q.answer()


@on("message", Command("id"))
async def id_cmd(message: Message):
    uid = message.from_user.id if message.from_user else "anonymous"
    await message.answer(f"🆔 Your ID: <code>{uid}</code>\n💬 Chat ID: <code>{message.chat.id}</code>")


@on("message", Command("optout"), PRIVATE_F)
async def optout(message: Message, bot: Bot):
    await db.users.update_one({"bot_id": bot.id, "user_id": message.from_user.id}, {"$set": {"opt_in": False}}, upsert=True)
    await message.answer("🔕 Ab aapko broadcast nahi milega. Wapas ke liye /optin")


@on("message", Command("optin"), PRIVATE_F)
async def optin(message: Message, bot: Bot):
    await db.users.update_one({"bot_id": bot.id, "user_id": message.from_user.id}, {"$set": {"opt_in": True}}, upsert=True)
    await message.answer("🔔 Aap wapas broadcast list me aa gaye.")


@on("message", Command("unreg"), GROUP_F)
async def unreg_cmd(message: Message, bot: Bot):
    if message.from_user:
        await db.members.update_one({"bot_id": bot.id, "chat_id": message.chat.id, "user_id": message.from_user.id},
                                    {"$set": {"opt_out": True, "name": message.from_user.first_name, "username": message.from_user.username}}, upsert=True)
        await message.answer("✅ Ab aap tag list se bahar ho. Wapas aane ke liye /reg")


@on("message", Command("reg"), GROUP_F)
async def reg_cmd(message: Message, bot: Bot):
    if message.from_user:
        await db.members.update_one({"bot_id": bot.id, "chat_id": message.chat.id, "user_id": message.from_user.id},
                                    {"$set": {"opt_out": False, "left": False, "name": message.from_user.first_name, "username": message.from_user.username}}, upsert=True)
        await message.answer("✅ Aap wapas tag list me aa gaye.")


# ═══════════════════════════ TAGGING ═══════════════════════════
TITLES = {"all": "TAG ALL", "admins": "CALLING ADMINS", "anybody": "LUCKY ONE", "gmtag": "GOOD MORNING", "gntag": "GOOD NIGHT", "vctag": "VC INVITE", "tagall": "TAG ALL • FUN"}
GM = ["Good Morning ji! ☀️ Uth jao, chai thandi ho rahi hai ☕", "Subah ho gayi mamu! 🌅 Ab to aankhein khol lo 😄", "Good Morning! 🌸 Aaj ka din tumhare naam ✨",
      "Rise & Shine 🌞 Phone chhodo, muh dhoo lo 😂", "Suprabhat 🙏 Aaj kuch accha karna hai, sirf scroll nahi 😎", "Good Morning 💫 Smile karo, aaj din mast jayega 😊"]
GN = ["Good Night 🌙 Phone rakho aur so jao 😴", "Shubh Ratri ✨ Sapno me milte hain 💤", "Good Night 🌌 Kal phir se masti karenge 😄",
      "Raat bahut ho gayi 🌃 Ab so jao, kal exam nahi to bhi 😂", "Sweet Dreams 💖 Subah milte hain, bye 👋", "Good Night 🌙 Charging pe laga do khud ko 🔋"]
VC = ["VC me aao sab log! 🎙️ Maza aayega 🔥", "Voice chat chalu hai 🎧 Jaldi join karo!", "Sab VC me aa jao yaar, akela bore ho raha hu 😭🎙️", "Mic ready karo 🎤 VC me party chal rahi hai 🥳"]
FUNNY = ["Oye! Kidhar ho? Group me aao 😂", "Tumhe dhundh dhundh ke thak gaya hu 🥲", "Bhai/Behen, zinda ho? Reply to karo 😆", "Ek message ka sawaab hai, chhupo mat 😎",
         "Aaj tumhari baari hai, bach ke kahan jaoge 😜", "Phone ka network theek hai? Group me aa jao 🤣", "Tumhare bina group adhura hai 🥺💖",
         "Hello hello? Mic check 1 2 3 🎤😂", "Online ho ya sirf last seen chhupa rakha hai? 🕵️", "Chai pee ke aa jao, hum wait kar rahe hain ☕😄"]
POOL = {"gmtag": GM, "gntag": GN, "vctag": VC, "tagall": FUNNY}
EMOJIS = list("😀😎🥳🤩😍🔥⚡💫✨🌸🍀🦋🌈💎👑🎯🚀🎉💖🌟🍕🎧🐱🦁🐯🦄🌙☀️🍭")


def mention(m, style):
    name = esc((m["name"] or "User")[:25])
    if style == "emoji":
        return f'<a href="tg://user?id={m["id"]}">{random.choice(EMOJIS)}</a>'
    if style == "username" and m.get("username"):
        return f"@{m['username']}"
    if style == "plain":
        return f"<b>{name}</b>"
    return f'<a href="tg://user?id={m["id"]}">{name}</a>'


def tg_kb(paused):
    first = B("▶️ Resume", "tg:resume") if paused else B("⏸ Pause", "tg:pause")
    return K([[first, B("⛔ Stop", "tg:stop")]])


def progress(done, total, state):
    n = int(10 * done / total) if total else 0
    return f"💠 <b>{S('tagging')}</b> • {state}\n<code>{'▰' * n}{'▱' * (10 - n)}</code>  <b>{done}/{total}</b>"


def build(cfg, mode, text_fn, batch):
    style, theme, font = cfg["style"], cfg["theme"], cfg["font"]
    ments = [mention(m, style) for m in batch]
    mline = " ".join(ments) if style == "emoji" else "\n".join(f"{BULLET.get(theme, '•')} {x}" for x in ments)
    text = text_fn()
    body = (f_html(text, font) + "\n\n" if text else "") + mline
    return wrap(theme, f(TITLES[mode], font), body)


async def send_batch(bot, cid, batch, cfg, mode, text_fn):
    msg = build(cfg, mode, text_fn, batch)
    if len(msg) > 3900 and len(batch) > 1:
        h = len(batch) // 2
        await send_batch(bot, cid, batch[:h], cfg, mode, text_fn)
        await send_batch(bot, cid, batch[h:], cfg, mode, text_fn)
        return
    for _ in range(5):
        try:
            await bot.send_message(cid, msg)
            return
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)


async def sync_admins(bot, cid):
    """Seeds the member DB with admins (Bot API cannot list all members)."""
    k = (bot.id, cid)
    if time.time() - _admsync.get(k, 0) < 600:
        return
    _admsync[k] = time.time()
    try:
        admins = [a.user for a in await bot.get_chat_administrators(cid) if not a.user.is_bot]
    except TelegramAPIError:
        return
    for u in admins:
        await track_member(bot.id, cid, u, force=True)
    await db.admins.update_one({"bot_id": bot.id, "chat_id": cid}, {"$set": {"admins": [u.id for u in admins], "updated": now_str()}}, upsert=True)


async def admin_members(bot, cid):
    try:
        admins = [a.user for a in await bot.get_chat_administrators(cid) if not a.user.is_bot]
    except TelegramAPIError:
        return []
    out_ids = {d["user_id"] async for d in db.members.find({"bot_id": bot.id, "chat_id": cid, "opt_out": True})}
    return [{"id": u.id, "name": u.first_name, "username": u.username} for u in admins if u.id not in out_ids]


async def run_tag(bot, message, members, cfg, mode, text_fn):
    cid, bid = message.chat.id, bot.id
    uid = message.from_user.id if message.from_user else 0
    total = len(members)
    if not total:
        return await message.answer("⚠️ Abhi koi member yaad nahi hai. Jaise-jaise log group me message karenge ya join karenge, list banti jayegi.")
    separate = mode == "tagall"
    per = 1 if separate else int(cfg["per"])
    st = {"stop": False, "paused": False, "go": asyncio.Event(), "by": uid}
    st["go"].set()
    RUN[(bid, cid)] = st
    sess = await db.tag_sessions.insert_one({"bot_id": bid, "chat_id": cid, "mode": mode, "by": uid, "total": total, "status": "running", "started": now_str()})
    ctl = await message.answer(progress(0, total, "▶️ running") + ("\n\nℹ️ <i>Bot sirf unhe tag kar sakta hai jinhe usne dekha hai (message/join).</i>" if total < 10 else ""), reply_markup=tg_kb(False))
    done, err = 0, None
    try:
        for i in range(0, total, per):
            await st["go"].wait()
            if st["stop"]:
                break
            batch = members[i:i + per]
            await send_batch(bot, cid, batch, cfg, mode, text_fn)
            done += len(batch)
            with contextlib.suppress(TelegramAPIError):
                await ctl.edit_text(progress(done, total, "⏸ paused" if st["paused"] else "▶️ running"), reply_markup=tg_kb(st["paused"]))
            await asyncio.sleep(3 if separate else 2.5)
    except TelegramForbiddenError:
        err = "bot ko group se hata diya gaya"
    except Exception as e:
        err = str(e)
        log.warning("tagging error: %s", e)
        await send_log(f"⚠️ <b>Tag error</b>\n🏠 {esc(message.chat.title)}\n🆔 <code>{cid}</code>\n<code>{esc(err[:200])}</code>")
    finally:
        RUN.pop((bid, cid), None)
    status = "error" if err else "stopped" if st["stop"] else "completed"
    await db.tag_sessions.update_one({"_id": sess.inserted_id}, {"$set": {"status": status, "done": done, "ended": now_str()}})
    end = (f"⚠️ <b>{S('error')}</b>: <code>{esc(err[:100])}</code>" if err else
           f"⛔ <b>{S('stopped')}</b> • {done}/{total}" if st["stop"] else f"✅ <b>{S('completed')}</b> • {done}/{total}")
    with contextlib.suppress(TelegramAPIError):
        await ctl.edit_text(end)


async def start_tag(bot, message, mode, silent=False):
    bid, cid = bot.id, message.chat.id
    cfg = await get_cfg(bid, cid)
    level = cfg["who_tagall"] if mode == "tagall" else cfg["who_all"]
    if not await can_use(bot, message, level):
        if not silent:
            names = {"staff": "admins", "owner": "group owner", "botowner": "bot owner"}
            await message.answer(f"⛔ Ye command sirf <b>{names.get(level, 'allowed users')}</b> use kar sakte hain.")
        return
    if (bid, cid) in RUN:
        if not silent:
            await message.answer("⏳ Tagging pehle se chal rahi hai. Rokne ke liye /stop.")
        return
    await reg_group(bid, message.chat)
    await sync_admins(bot, cid)
    custom = strip_cmd(message.html_text)
    members = await (admin_members(bot, cid) if mode == "admins" else db_members(bid, cid))
    if mode == "anybody" and members:
        members = [random.choice(members)]
    if cfg["limit"] and mode != "anybody":
        members = members[: int(cfg["limit"])]
    if custom:
        text_fn = lambda: custom  # noqa: E731
    elif mode in POOL:
        text_fn = lambda: random.choice(POOL[mode])  # noqa: E731
    else:
        text_fn = lambda: ""  # noqa: E731
    await run_tag(bot, message, members, cfg, mode, text_fn)


def _tag_handler(mode):
    async def h(message: Message, bot: Bot):
        await start_tag(bot, message, mode)
    return h


for _m in ("all", "admins", "anybody", "gmtag", "gntag", "vctag", "tagall"):
    _REG.append(("message", (Command(_m), GROUP_F), _tag_handler(_m)))


@on("message", GROUP_F, F.text.regexp(r"(?i)^(@all|all)(\s|$)"))
async def p_all(message: Message, bot: Bot):
    await start_tag(bot, message, "all", silent=True)


@on("message", GROUP_F, F.text.regexp(r"(?i)^@admins?(\s|$)"))
async def p_admin(message: Message, bot: Bot):
    await start_tag(bot, message, "admins", silent=True)


@on("message", Command("stop"), GROUP_F)
async def stop_cmd(message: Message, bot: Bot):
    st = RUN.get((bot.id, message.chat.id))
    if not st:
        return await message.answer("ℹ️ Abhi koi tagging nahi chal rahi.")
    uid = message.from_user.id if message.from_user else 0
    if uid != st["by"] and not await can_use(bot, message, "staff"):
        return await message.answer("⛔ Sirf admins ya tagging shuru karne wala rok sakta hai.")
    st["stop"] = True
    st["go"].set()
    await message.answer("⛔ Tagging rok di gayi.")


@on("callback_query", F.data.in_({"tg:pause", "tg:resume", "tg:stop"}))
async def tg_cb(q: CallbackQuery, bot: Bot):
    cid = q.message.chat.id
    st = RUN.get((bot.id, cid))
    if not st:
        return await q.answer("Tagging chal nahi rahi.", show_alert=True)
    if q.from_user.id != st["by"] and not await is_admin(bot, cid, q.from_user.id):
        return await q.answer("⛔ Sirf admins control kar sakte hain.", show_alert=True)
    act = q.data.split(":")[1]
    if act == "pause":
        st["paused"] = True
        st["go"].clear()
        await q.answer("⏸ Paused")
    elif act == "resume":
        st["paused"] = False
        st["go"].set()
        await q.answer("▶️ Resumed")
    else:
        st["stop"] = True
        st["go"].set()
        return await q.answer("⛔ Stopped")
    with contextlib.suppress(TelegramAPIError):
        await q.message.edit_reply_markup(reply_markup=tg_kb(st["paused"]))


# ═══════════════════════════ SETTINGS ═══════════════════════════
PER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 100]
WHO = [("all", "🌍 Everyone"), ("staff", "🛡 Staff"), ("owner", "👑 Group Owner"), ("botowner", "🤖 Bot Owner")]
SCHEMA = {
    "style": ("🎨 Tag Style", [("emoji", "😎 Emoji"), ("username", "🔗 Username"), ("mention", "👤 Mention"), ("plain", "🔤 Plain Name")]),
    "per": ("📦 Per Message", [(str(n), str(n)) for n in PER]),
    "limit": ("🎯 Tag Limit", [("10", "10"), ("25", "25"), ("50", "50"), ("100", "100"), ("0", "All")]),
    "font": ("🔠 Font", list(FONT_NAMES.items())),
    "theme": ("🌈 Theme", list(THEME_NAMES.items())),
    "who_all": ("👑 /all Access", WHO),
    "who_tagall": ("😂 /tagall Access", WHO),
}


def label(key, val):
    return next((lab for v, lab in SCHEMA[key][1] if v == str(val)), str(val))


def main_text(cfg):
    oo = lambda v: "ON" if v else "OFF"  # noqa: E731
    rows = [f"🎨 {S('style')}  ›  <b>{label('style', cfg['style'])}</b>", f"📦 {S('per message')}  ›  <b>{cfg['per']}</b>",
            f"🎯 {S('limit')}  ›  <b>{label('limit', cfg['limit'])}</b>", f"🔠 {S('font')}  ›  <b>{label('font', cfg['font'])}</b>",
            f"🌈 {S('theme')}  ›  <b>{label('theme', cfg['theme'])}</b>", f"👑 /all  ›  <b>{label('who_all', cfg['who_all'])}</b>",
            f"😂 /tagall  ›  <b>{label('who_tagall', cfg['who_tagall'])}</b>",
            f"👋 {S('welcome')}  ›  <b>{oo(cfg['welcome'])}</b>   🚪 {S('left')}  ›  <b>{oo(cfg['left'])}</b>"]
    return wrap("neon", S("kuku settings"), "\n".join(rows))


def kb_main(cfg):
    dot = lambda v: "🟢" if v else "🔴"  # noqa: E731
    return K([[B("🎨 Style", "st:menu:style"), B("📦 Per Msg", "st:menu:per")], [B("🎯 Limit", "st:menu:limit"), B("🔠 Font", "st:menu:font")],
              [B("🌈 Theme", "st:menu:theme"), B("👑 /all Access", "st:menu:who_all")], [B("😂 /tagall Access", "st:menu:who_tagall")],
              [B(f"{dot(cfg['welcome'])} Welcome", "st:tog:welcome"), B(f"{dot(cfg['left'])} Left", "st:tog:left")], [B("✖️ Close", "st:close")]])


def kb_menu(cfg, key):
    cur = str(cfg[key])
    btns = [B(("✅ " if v == cur else "") + lab, f"st:set:{key}:{v}") for v, lab in SCHEMA[key][1]]
    cols = 4 if key == "per" else 3 if key == "limit" else 2
    rows = [btns[i:i + cols] for i in range(0, len(btns), cols)]
    rows.append([B("⬅️ Back", "st:main")])
    return K(rows)


async def show(q, text, markup):
    with contextlib.suppress(TelegramBadRequest):
        await q.message.edit_text(text, reply_markup=markup)


@on("message", Command("settings"))
async def settings_cmd(message: Message, bot: Bot):
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer("⚙️ Settings group me kholo (mujhe admin banake <code>/settings</code> likho).")
    if not await can_use(bot, message, "staff"):
        return await message.answer("⛔ Settings sirf admins badal sakte hain.")
    await reg_group(bot.id, message.chat)
    cfg = await get_cfg(bot.id, message.chat.id)
    await message.answer(main_text(cfg), reply_markup=kb_main(cfg))


@on("callback_query", F.data.startswith("st:"))
async def settings_cb(q: CallbackQuery, bot: Bot):
    cid = q.message.chat.id
    if not await is_admin(bot, cid, q.from_user.id):
        return await q.answer("🛡 Sirf admins settings badal sakte hain.", show_alert=True)
    parts = q.data.split(":")
    act, cfg = parts[1], await get_cfg(bot.id, cid)
    if act == "close":
        with contextlib.suppress(TelegramAPIError):
            await q.message.delete()
        return await q.answer()
    if act == "main":
        await show(q, main_text(cfg), kb_main(cfg))
    elif act == "menu":
        key = parts[2]
        await show(q, wrap("neon", S(SCHEMA[key][0].split(" ", 1)[1]), f"{SCHEMA[key][0]}\n\n👇 {S('select an option')}"), kb_menu(cfg, key))
    elif act == "set":
        key, val = parts[2], parts[3]
        await set_cfg(bot.id, cid, key, int(val) if key in ("per", "limit") else val)
        cfg = await get_cfg(bot.id, cid)
        await show(q, wrap("neon", S(SCHEMA[key][0].split(" ", 1)[1]), f"✅ {S('saved')}: <b>{label(key, val)}</b>"), kb_menu(cfg, key))
        return await q.answer("✅ Saved")
    elif act == "tog":
        await set_cfg(bot.id, cid, parts[2], not cfg[parts[2]])
        await show(q, main_text(await get_cfg(bot.id, cid)), kb_main(await get_cfg(bot.id, cid)))
    await q.answer()


# ═══════════════════════════ WELCOME / LEFT / BOT ADDED-REMOVED ═══════════════════════════
@on("message", F.new_chat_members)
async def welcome(message: Message, bot: Bot):
    chat, cfg = message.chat, await get_cfg(bot.id, message.chat.id)
    for u in message.new_chat_members:
        if u.is_bot:
            continue
        await track_member(bot.id, chat.id, u, force=True)
        if not cfg["welcome"]:
            continue
        try:
            count = await bot.get_chat_member_count(chat.id)
        except TelegramAPIError:
            count = "?"
        body = (f"👤 {S('name')}  ›  {ulink(u)}\n🆔 {S('id')}  ›  <code>{u.id}</code>\n"
                f"🔗 {S('username')}  ›  {'@' + u.username if u.username else S('none')}\n"
                f"🏠 {S('group')}  ›  <b>{esc(chat.title)}</b>\n👥 {S('members')}  ›  <b>{count}</b>\n\n"
                f"🤖 {S('want your own tag bot? make a clone below')}")
        cap = wrap("neon", S("welcome"), body)
        try:
            data = await group_photo(bot, chat.id)
            if data:
                await bot.send_photo(chat.id, BufferedInputFile(data, "group.jpg"), caption=cap, reply_markup=clone_kb())
            else:
                await bot.send_message(chat.id, cap, reply_markup=clone_kb())
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except TelegramAPIError as e:
            log.warning("welcome error: %s", e)


@on("message", F.left_chat_member)
async def left(message: Message, bot: Bot):
    u = message.left_chat_member
    if u.is_bot:
        return
    await db.members.update_one({"bot_id": bot.id, "chat_id": message.chat.id, "user_id": u.id}, {"$set": {"left": True}})
    if (await get_cfg(bot.id, message.chat.id))["left"]:
        with contextlib.suppress(TelegramAPIError):
            await bot.send_message(message.chat.id, wrap("neon", S("goodbye"), f"👋 {ulink(u)} {S('left the group')} 😢\n💔 {S('bye bye, take care')} ✨"))


@on("my_chat_member")
async def bot_status(ev: ChatMemberUpdated, bot: Bot):
    chat, new, old = ev.chat, ev.new_chat_member.status, ev.old_chat_member.status
    if chat.type == ChatType.PRIVATE:
        if new == ChatMemberStatus.KICKED:
            await db.users.update_one({"bot_id": bot.id, "user_id": chat.id}, {"$set": {"blocked": True}})
        elif new == ChatMemberStatus.MEMBER:
            await db.users.update_one({"bot_id": bot.id, "user_id": chat.id}, {"$set": {"blocked": False}})
        return
    via = "" if is_master(bot) else f"\n• Via clone: @{CTX[bot.id]['username']}"
    adder = ev.from_user
    if new in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR) and old in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        await reg_group(bot.id, chat)
        await db.groups.update_one({"bot_id": bot.id, "chat_id": chat.id}, {"$set": {"active": True}})
        try:
            count = await bot.get_chat_member_count(chat.id)
        except TelegramAPIError:
            count = "?"
        total = await db.groups.count_documents({"bot_id": bot.id, "active": {"$ne": False}})
        await send_log(f"➕ <b>Bot Added To Group</b>\n\n• Group: <b>{esc(chat.title)}</b>\n• ID: <code>{chat.id}</code>\n"
                       f"• Username: {'@' + chat.username if chat.username else 'Private'}\n• Members: <b>{count}</b>\n"
                       f"• Added by: {ulink(adder)}" + (f" (@{adder.username})" if adder.username else "") + f"\n• Adder ID: <code>{adder.id}</code>\n"
                       f"• Time: {now_str()}\n• Total groups: <b>{total}</b>{via}")
        with contextlib.suppress(TelegramAPIError):
            await bot.send_message(chat.id, wrap("neon", S("thanks for adding me"),
                f"⚡ <b>{S('kuku tag bot')}</b> {S('is ready')}!\n\n🛡 {S('make me admin to tag everyone')}\n⚙️ /settings  •  📖 /start"), reply_markup=clone_kb())
    elif new in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        await db.groups.update_one({"bot_id": bot.id, "chat_id": chat.id}, {"$set": {"active": False}})
        await send_log(f"➖ <b>Bot Removed From Group</b>\n\n• Group: <b>{esc(chat.title)}</b>\n• ID: <code>{chat.id}</code>\n"
                       f"• Removed by: {ulink(adder)}\n• Time: {now_str()}{via}")


# ═══════════════════════════ EXACT-COPY BROADCAST ═══════════════════════════
def url_markup(m):
    mk = getattr(m, "reply_markup", None)
    if not mk:
        return None
    rows = [[b for b in row if b.url] for row in mk.inline_keyboard]
    rows = [r for r in rows if r]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def get_source(message):
    """('copy'|'album'|'text', ...). Replied message is copied exactly as Telegram stored it."""
    r = message.reply_to_message
    if r:
        ids = ALBUMS.get((r.chat.id, r.media_group_id)) if r.media_group_id else None
        if ids:
            return ("album", r.chat.id, sorted(set(ids)))
        return ("copy", r.chat.id, r.message_id, url_markup(r))
    text = strip_cmd(message.html_text)
    return ("text", text) if text else None


async def send_source(bot, cid, src):
    if src[0] == "copy":
        await bot.copy_message(cid, src[1], src[2], reply_markup=src[3])
    elif src[0] == "album":
        await bot.copy_messages(cid, src[1], src[2])
    else:
        await bot.send_message(cid, src[1])


async def send_retry(bot, cid, sender):
    for _ in range(3):
        try:
            await sender(cid)
            return "ok"
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            return "blocked"
        except TelegramAPIError as e:
            return str(e)[:60]
    return "flood"


async def mark_dead(bid, cid):
    if cid > 0:
        await db.users.update_one({"bot_id": bid, "user_id": cid}, {"$set": {"blocked": True}})
    else:
        await db.groups.update_one({"bot_id": bid, "chat_id": cid}, {"$set": {"active": False}})


def bc_progress(label_, i, total, ok, fail, blocked):
    return (f"📣 <b>{S('broadcasting')}</b> • {label_}\n<code>{i}/{total}</code>\n✅ {ok}   🚫 {blocked}   ❌ {fail}")


async def run_broadcast(bot, message, sender, targets, label_, kind):
    bid = bot.id
    if bid in BC:
        return await message.answer("⏳ Ek broadcast pehle se chal raha hai.")
    targets = list(dict.fromkeys(targets))  # duplicate prevention
    total = len(targets)
    if not total:
        return await message.answer("⚠️ Koi target nahi mila.")
    st = {"stop": False}
    BC[bid] = st
    ctl = await message.answer(bc_progress(label_, 0, total, 0, 0, 0), reply_markup=K([[B("⛔ Stop", "bc:stop")]]))
    ok = fail = blocked = 0
    failed, last, i = [], time.time(), 0
    try:
        for i, cid in enumerate(targets, 1):
            if st["stop"]:
                i -= 1
                break
            res = await send_retry(bot, cid, sender)
            if res == "ok":
                ok += 1
            elif res == "blocked":
                blocked += 1
                failed.append({"id": cid, "why": "blocked"})
                await mark_dead(bid, cid)
            else:
                fail += 1
                failed.append({"id": cid, "why": res})
            if time.time() - last > 3:
                last = time.time()
                with contextlib.suppress(TelegramAPIError):
                    await ctl.edit_text(bc_progress(label_, i, total, ok, fail, blocked), reply_markup=K([[B("⛔ Stop", "bc:stop")]]))
            await asyncio.sleep(0.05)
    finally:
        BC.pop(bid, None)
    await db.broadcast_logs.insert_one({"bot_id": bid, "kind": kind, "time": time.time(), "total": total, "ok": ok, "failed": fail, "blocked": blocked, "stopped": st["stop"], "failed_list": failed[:300]})
    head = "⛔ Broadcast stopped" if st["stop"] else "✅ Broadcast done"
    with contextlib.suppress(TelegramAPIError):
        await ctl.edit_text(f"{head}\n\n📬 Sent: <b>{ok}</b>\n🚫 Blocked: <b>{blocked}</b>\n❌ Failed: <b>{fail}</b>\n📊 Total: <b>{total}</b>\n\n/bclog — failed report")


@on("callback_query", F.data == "bc:stop")
async def bc_stop(q: CallbackQuery, bot: Bot):
    if not is_owner(bot, q.from_user.id):
        return await q.answer("⛔ Sirf owner", show_alert=True)
    st = BC.get(bot.id)
    if st:
        st["stop"] = True
    await q.answer("⛔ Stopping...")


async def _targets(bid, kind):
    if kind == "users":
        return [d["user_id"] async for d in db.users.find({"bot_id": bid, "opt_in": {"$ne": False}, "blocked": {"$ne": True}})]
    return [d["chat_id"] async for d in db.groups.find({"bot_id": bid, "active": {"$ne": False}})]


USAGE_BC = "Kisi message par <b>reply</b> karke <code>/broadcast</code> likho (exact copy jayega), ya <code>/broadcast text</code>."


@on("message", Command("broadcast"), BotOwner())
async def bc_users(message: Message, bot: Bot):
    src = get_source(message)
    if not src:
        return await message.answer(USAGE_BC)
    await run_broadcast(bot, message, lambda cid: send_source(bot, cid, src), await _targets(bot.id, "users"), "users", "users")


@on("message", Command("gcast"), BotOwner())
async def bc_groups(message: Message, bot: Bot):
    src = get_source(message)
    if not src:
        return await message.answer(USAGE_BC.replace("/broadcast", "/gcast"))
    await run_broadcast(bot, message, lambda cid: send_source(bot, cid, src), await _targets(bot.id, "groups"), "groups", "groups")


@on("message", Command("bclog"), BotOwner())
async def bclog(message: Message, bot: Bot):
    d = await db.broadcast_logs.find_one({"bot_id": bot.id}, sort=[("time", -1)])
    if not d:
        return await message.answer("Abhi koi broadcast log nahi.")
    reasons = {}
    for x in d.get("failed_list", []):
        reasons[x["why"]] = reasons.get(x["why"], 0) + 1
    rs = "\n".join(f"• {esc(k)}: {v}" for k, v in sorted(reasons.items(), key=lambda a: -a[1])[:8]) or "• none"
    await message.answer(f"📋 <b>Last broadcast ({d['kind']})</b>\n\nTotal {d['total']} • ✅ {d['ok']} • 🚫 {d['blocked']} • ❌ {d['failed']}\n\n<b>Failure reasons</b>\n{rs}")


# ---- /ucast: master -> opted-in users of all running clones ----
KIND_FILE = {"photo": "file.jpg", "video": "file.mp4", "document": "file.bin", "animation": "file.mp4", "audio": "file.mp3", "voice": "file.ogg", "sticker": "file.webp"}


def payload_of(m):
    cap = m.html_text or ""
    if m.photo:
        return "photo", m.photo[-1].file_id, cap
    for k in ("video", "document", "animation", "audio", "voice", "sticker"):
        obj = getattr(m, k)
        if obj:
            return k, obj.file_id, "" if k == "sticker" else cap
    return ("text", None, cap) if m.text else None


async def send_payload(bot, cid, kind, media, text):
    if kind == "text":
        return await bot.send_message(cid, text)
    kw = {kind: media}
    if kind != "sticker":
        kw["caption"] = text or None
    return await getattr(bot, f"send_{kind}")(cid, **kw)


@on("message", Command("ucast"), MasterSudo())
async def ucast(message: Message, bot: Bot):
    r = message.reply_to_message
    p = payload_of(r) if r else (("text", None, strip_cmd(message.html_text)) if strip_cmd(message.html_text) else None)
    if not p:
        return await message.answer("Kisi message par reply karke <code>/ucast</code> likho (text, photo, video, document, audio, voice, GIF, sticker).")
    if bid_busy := BC.get("ucast"):
        return await message.answer("⏳ Clone broadcast pehle se chal raha hai.")
    kind, fid, text = p
    media = None
    if kind != "text":
        buf = await bot.download(fid)
        media = BufferedInputFile(buf.read(), KIND_FILE[kind])
    BC["ucast"] = {"stop": False}
    ctl = await message.answer("📣 Clone broadcast shuru...")
    lines, tot_ok, tot_fail = [], 0, 0
    try:
        for doc in [d async for d in db.clones.find({"enabled": True, "active": True})]:
            rt = RT.get(doc["bot_id"])
            if not rt:
                lines.append(f"• @{esc(doc['username'])}: ⏸ not running")
                continue
            cbot, ok, fail, cmedia = rt["bot"], 0, 0, media
            for cid in await _targets(doc["bot_id"], "users"):
                try:
                    sent = await send_payload(cbot, cid, kind, cmedia, text)
                    ok += 1
                    if kind != "text" and not isinstance(cmedia, str):
                        obj = getattr(sent, kind)
                        cmedia = (obj[-1] if isinstance(obj, list) else obj).file_id  # reuse file_id for the rest
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after + 1)
                    fail += 1
                except TelegramForbiddenError:
                    fail += 1
                    await mark_dead(doc["bot_id"], cid)
                except TelegramAPIError:
                    fail += 1
                await asyncio.sleep(0.05)
            tot_ok += ok
            tot_fail += fail
            lines.append(f"• @{esc(doc['username'])}: ✅ {ok}  ❌ {fail}")
            await db.broadcast_logs.insert_one({"bot_id": doc["bot_id"], "kind": "ucast", "time": time.time(), "total": ok + fail, "ok": ok, "failed": fail, "blocked": 0, "failed_list": []})
    finally:
        BC.pop("ucast", None)
    await ctl.edit_text("✅ <b>Clone broadcast done</b>\n\n" + ("\n".join(lines) or "Koi running clone nahi.") + f"\n\n📬 Sent: <b>{tot_ok}</b> • ❌ Failed: <b>{tot_fail}</b>")


# ═══════════════════════════ OWNER / SUDO COMMANDS ═══════════════════════════
@on("message", Command("ping"), BotOwner())
async def ping_cmd(message: Message):
    t = time.time()
    r = await message.answer("🏓 ...")
    await r.edit_text(f"🏓 <b>Pong!</b> <code>{int((time.time() - t) * 1000)} ms</code>")


@on("message", Command("stats"), BotOwner())
async def stats_cmd(message: Message, bot: Bot):
    bid = bot.id
    up = int(time.time() - START_TIME)
    d, r = divmod(up, 86400)
    h, r = divmod(r, 3600)
    rows = [f"👤 {S('users')}  ›  <b>{await db.users.count_documents({'bot_id': bid})}</b>",
            f"🔔 {S('opted in')}  ›  <b>{await db.users.count_documents({'bot_id': bid, 'opt_in': {'$ne': False}})}</b>",
            f"👥 {S('groups')}  ›  <b>{await db.groups.count_documents({'bot_id': bid, 'active': {'$ne': False}})}</b>",
            f"🧾 {S('members tracked')}  ›  <b>{await db.members.count_documents({'bot_id': bid})}</b>",
            f"🚫 {S('banned')}  ›  <b>{await db.banned_users.count_documents({'bot_id': bid})}</b>",
            f"🏷 {S('active tagging')}  ›  <b>{sum(1 for k in RUN if k[0] == bid)}</b>"]
    if is_master(bot):
        rows += [f"🤖 {S('clones')}  ›  <b>{await db.clones.count_documents({})}</b> ({len(RT)} running)", f"🛡 {S('sudo')}  ›  <b>{len(SUDO)}</b>"]
    rows.append(f"⏱ {S('uptime')}  ›  <b>{d}d {h}h {r // 60}m</b>")
    await message.answer(wrap("neon", S("bot stats"), "\n".join(rows)))


async def _id_arg(message):
    parts = (message.text or "").split()
    if message.reply_to_message and message.reply_to_message.from_user and len(parts) < 2:
        return message.reply_to_message.from_user.id
    if len(parts) < 2:
        await message.answer("Usage: <code>/ban user_or_group_id</code> (ya reply karo)")
        return None
    try:
        return int(parts[1])
    except ValueError:
        await message.answer("❌ ID number honi chahiye.")
        return None


@on("message", Command("ban"), BotOwner())
async def ban_cmd(message: Message, bot: Bot):
    i = await _id_arg(message)
    if i is None:
        return
    if i == OWNER_ID or i == CTX[bot.id]["owner_id"]:
        return await message.answer("😅 Owner ko ban nahi kar sakte.")
    await db.banned_users.update_one({"bot_id": bot.id, "target_id": i}, {"$set": {"ok": True}}, upsert=True)
    _bans.setdefault(bot.id, set()).add(i)
    await message.answer(f"🚫 Banned: <code>{i}</code>")


@on("message", Command("unban"), BotOwner())
async def unban_cmd(message: Message, bot: Bot):
    i = await _id_arg(message)
    if i is None:
        return
    await db.banned_users.delete_one({"bot_id": bot.id, "target_id": i})
    _bans.setdefault(bot.id, set()).discard(i)
    await message.answer(f"✅ Unbanned: <code>{i}</code>")


@on("message", Command("groups"), BotOwner())
async def groups_cmd(message: Message, bot: Bot):
    docs = [d async for d in db.groups.find({"bot_id": bot.id, "active": {"$ne": False}}).limit(60)]
    if not docs:
        return await message.answer("Abhi koi group nahi.")
    await message.answer("👥 <b>Groups</b>\n\n" + "\n".join(f"{i}. {esc(d.get('title'))[:30]} — <code>{d['chat_id']}</code>" for i, d in enumerate(docs, 1))[:3900])


@on("message", Command(re.compile(r"^setsupport\d*$")), BotOwner())
async def setsupport(message: Message, bot: Bot, command: CommandObject):
    num = re.sub(r"\D", "", command.command) or "1"
    url, name = split_link_name((command.args or "").split())
    if not url:
        return await message.answer(f"Usage: <code>/setsupport{'' if num == '1' else num} https://t.me/xyz Support Group</code>\n(link aur naam kisi bhi order me)")
    name = (name or f"💬 Support {num}")[:40]
    await db.support_links.update_one({"bot_id": bot.id, "key": num}, {"$set": {"url": url, "name": name}}, upsert=True)
    _sup.pop(bot.id, None)
    await message.answer(f"✅ Support button #{num} set:\n<b>{esc(name)}</b>\n{esc(url)}")


@on("message", Command("delsupport"), BotOwner())
async def delsupport(message: Message, bot: Bot, command: CommandObject):
    if not command.args:
        return await message.answer("Usage: <code>/delsupport 2</code>")
    r = await db.support_links.delete_one({"bot_id": bot.id, "key": command.args.strip()})
    _sup.pop(bot.id, None)
    await message.answer(f"🗑 Support #{esc(command.args.strip())} hata diya." if r.deleted_count else "❌ Ye number nahi mila. /supports dekho.")


@on("message", Command("supports"), BotOwner())
async def supports(message: Message, bot: Bot):
    links = await get_meta_links(bot.id)
    lines = [f"#{k}  {esc(v['name'])} — {esc(v['url'])}" for k, v in sorted(links.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0) if k != "owner"]
    own = links.get("owner")
    await message.answer("💬 <b>Support buttons</b>\n\n" + ("\n".join(lines) or "Koi nahi.") + f"\n\n👑 <b>Owner button</b>\n{esc(own['name'] + ' — ' + own['url']) if own else 'Default (owner ID)'}")


@on("message", Command("setowner"), BotOwner())
async def setowner(message: Message, bot: Bot, command: CommandObject):
    url, name = split_link_name((command.args or "").split())
    if not url:
        return await message.answer("Usage: <code>/setowner @username Owner</code> (ya link / ID)")
    await db.support_links.update_one({"bot_id": bot.id, "key": "owner"}, {"$set": {"url": url, "name": (name or "👑 Owner")[:40]}}, upsert=True)
    _sup.pop(bot.id, None)
    await message.answer("✅ Owner button set ho gaya.")


# ---- master owner only ----
@on("message", Command("restart"), MasterOwner())
async def restart_cmd(message: Message):
    await message.answer("♻️ Restarting...")
    await asyncio.sleep(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)


@on("message", Command("addsudo"), MasterOwner())
async def addsudo(message: Message, bot: Bot):
    i = await _id_arg(message)
    if i is None:
        return
    SUDO.add(i)
    await db.sudo.update_one({"user_id": i}, {"$set": {"ok": True}}, upsert=True)
    await setup_menus(bot)
    await message.answer(f"✅ Sudo added: <code>{i}</code>")


@on("message", Command("delsudo"), MasterOwner())
async def delsudo(message: Message, bot: Bot):
    i = await _id_arg(message)
    if i is None:
        return
    SUDO.discard(i)
    await db.sudo.delete_one({"user_id": i})
    with contextlib.suppress(TelegramAPIError):
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=i))
    await message.answer(f"🗑 Sudo removed: <code>{i}</code>" + ("\n(ENV SUDO_IDS wale ko variable se hatana padega)" if i in SUDO_ENV else ""))


SUDO_ENV = set(SUDO)


@on("message", Command("sudolist"), MasterOwner())
async def sudolist(message: Message):
    await message.answer("🛡 <b>Sudo users</b>\n\n" + ("\n".join(f"• <code>{i}</code>" for i in sorted(SUDO)) or "Koi sudo nahi."))


# ═══════════════════════════ CLONE SYSTEM ═══════════════════════════
def enc(token):
    return FERNET.encrypt(token.encode()).decode()


def dec(s):
    return FERNET.decrypt(s.encode()).decode()


def thash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def clone_status(doc):
    if doc["bot_id"] in RT:
        return "🟢 running"
    if not doc.get("enabled", True):
        return "⛔ disabled by master"
    if doc.get("status") == "invalid":
        return "❌ invalid token"
    return "⏸ stopped"


async def _poll(bot, dp, bid):
    try:
        await dp.start_polling(bot, handle_signals=False, close_bot_session=False)
    except asyncio.CancelledError:
        raise
    except TelegramUnauthorizedError:
        await db.clones.update_one({"bot_id": bid}, {"$set": {"status": "invalid"}})
        log.warning("clone %s token invalid", bid)
    except Exception as e:
        log.warning("clone %s polling stopped: %s", bid, e)
    finally:
        RT.pop(bid, None)
        CTX.pop(bid, None)


async def start_clone(doc):
    bid = doc["bot_id"]
    if bid in RT:
        return "already running"
    try:
        token = dec(doc["token_enc"])
    except InvalidToken:
        await db.clones.update_one({"bot_id": bid}, {"$set": {"status": "invalid"}})
        return "token decrypt failed (ENCRYPTION_KEY badla?)"
    bot = Bot(token, default=DEFAULT)
    try:
        me = await bot.get_me()
    except TelegramAPIError:
        await db.clones.update_one({"bot_id": bid}, {"$set": {"status": "invalid"}})
        await bot.session.close()
        return "token invalid ya revoke ho gaya"
    CTX[bid] = {"master": False, "owner_id": doc["owner_id"], "username": me.username}
    dp = build_dispatcher()
    RT[bid] = {"bot": bot, "dp": dp, "task": asyncio.create_task(_poll(bot, dp, bid))}
    await db.clones.update_one({"bot_id": bid}, {"$set": {"status": "running", "username": me.username, "active": True}})
    await setup_menus(bot)
    return None


async def stop_clone(bid):
    rt = RT.pop(bid, None)
    CTX.pop(bid, None)
    if not rt:
        return
    with contextlib.suppress(Exception):
        await rt["dp"].stop_polling()
    rt["task"].cancel()
    with contextlib.suppress(BaseException):
        await rt["task"]
    with contextlib.suppress(Exception):
        await rt["bot"].session.close()


async def delete_clone_data(bid):
    for col in (db.users, db.groups, db.members, db.settings, db.banned_users, db.support_links, db.admins, db.tag_sessions, db.broadcast_logs):
        await col.delete_many({"bot_id": bid})
    await db.clones.delete_one({"bot_id": bid})


async def find_clone(user_id, arg, any_owner=False):
    q = {} if any_owner else {"owner_id": user_id}
    if arg:
        a = arg.strip().lstrip("@").lower()
        docs = [d async for d in db.clones.find(q)]
        return next((d for d in docs if str(d["bot_id"]) == a or (d.get("username") or "").lower() == a), None)
    docs = [d async for d in db.clones.find(q).limit(2)]
    return docs[0] if len(docs) == 1 else None


@on("message", Command("clone"), PRIVATE_F, MasterAny())
async def clone_cmd(message: Message, bot: Bot, command: CommandObject):
    u = message.from_user
    token = (command.args or "").strip()
    if not token:
        return await message.answer(CLONE_GUIDE)
    with contextlib.suppress(TelegramAPIError):
        await message.delete()  # token must not stay in chat
    if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,}", token):
        return await bot.send_message(u.id, "❌ Token ka format galat hai.")
    if u.id != OWNER_ID and await db.clones.count_documents({"owner_id": u.id}) >= MAX_CLONES:
        return await bot.send_message(u.id, f"⚠️ Aap max {MAX_CLONES} clone bana sakte ho.")
    tmp = Bot(token, default=DEFAULT)
    try:
        me = await tmp.get_me()
    except TelegramAPIError:
        return await bot.send_message(u.id, "❌ Token invalid hai ya revoke ho chuka hai.")
    finally:
        await tmp.session.close()
    if me.id == MASTER.id or await db.clones.find_one({"$or": [{"bot_id": me.id}, {"token_hash": thash(token)}]}):
        return await bot.send_message(u.id, "⚠️ Ye bot pehle se connect hai.")
    doc = {"bot_id": me.id, "username": me.username, "name": me.full_name, "owner_id": u.id, "owner_name": u.full_name, "owner_username": u.username,
           "token_enc": enc(token), "token_hash": thash(token), "enabled": True, "active": True, "status": "new", "created": now_str()}
    await db.clones.insert_one(doc)
    err = await start_clone(doc)
    if err:
        return await bot.send_message(u.id, f"⚠️ Clone save hua par start nahi hua: {esc(err)}")
    await bot.send_message(u.id, f"✅ <b>Clone ready!</b> @{me.username}\n\n• BotFather me <code>/setprivacy</code> → Disable\n• Bot ko group me admin banao\n• Control: /myclones /stopclone /startclone /deleteclone")
    await send_log(f"🤖 <b>New Clone</b>\n• Bot: @{me.username} (<code>{me.id}</code>)\n• Owner: {ulink(u)} <code>{u.id}</code>\n• Time: {now_str()}")


@on("message", Command("myclones"), PRIVATE_F, MasterAny())
async def myclones(message: Message):
    docs = [d async for d in db.clones.find({"owner_id": message.from_user.id})]
    if not docs:
        return await message.answer("Aapka koi clone nahi. /clone se banao.")
    out = []
    for d in docs:
        u, g = await db.users.count_documents({"bot_id": d["bot_id"]}), await db.groups.count_documents({"bot_id": d["bot_id"], "active": {"$ne": False}})
        out.append(f"🤖 @{esc(d.get('username'))} — {clone_status(d)}\n   👤 {u} users • 👥 {g} groups")
    await message.answer("<b>Your clones</b>\n\n" + "\n\n".join(out))


def _clone_action(kind):
    async def h(message: Message, command: CommandObject):
        d = await find_clone(message.from_user.id, command.args)
        if not d:
            return await message.answer(f"Clone nahi mila. Usage: <code>/{kind}clone @botusername</code>")
        if kind == "stop":
            await stop_clone(d["bot_id"])
            await db.clones.update_one({"bot_id": d["bot_id"]}, {"$set": {"active": False, "status": "stopped"}})
            await message.answer(f"⏸ @{esc(d['username'])} band ho gaya.")
        elif kind == "start":
            if not d.get("enabled", True):
                return await message.answer("⛔ Master owner ne is clone ko disable kiya hai.")
            await db.clones.update_one({"bot_id": d["bot_id"]}, {"$set": {"active": True}})
            d["active"] = True
            err = await start_clone(d)
            await message.answer(f"🟢 @{esc(d['username'])} chalu ho gaya." if not err else f"⚠️ {esc(err)}")
        else:
            await stop_clone(d["bot_id"])
            await delete_clone_data(d["bot_id"])
            await message.answer(f"🗑 @{esc(d['username'])} aur uska data delete ho gaya.")
    return h


for _k in ("stop", "start", "delete"):
    _REG.append(("message", (Command(f"{_k}clone"), PRIVATE_F, MasterAny()), _clone_action(_k)))


# ---- master panel ----
@on("message", Command("clonelist"), MasterSudo())
async def clonelist(message: Message):
    docs = [d async for d in db.clones.find()]
    if not docs:
        return await message.answer("Koi clone connected nahi.")
    out = []
    for d in docs[:40]:
        u = await db.users.count_documents({"bot_id": d["bot_id"]})
        g = await db.groups.count_documents({"bot_id": d["bot_id"], "active": {"$ne": False}})
        out.append(f"🤖 @{esc(d.get('username'))} — {clone_status(d)}\n   👑 {esc(d.get('owner_name'))} (<code>{d['owner_id']}</code>)\n   👤 {u} users • 👥 {g} groups • 📅 {esc(d.get('created'))}")
    await message.answer(f"<b>Clones ({len(docs)} • {len(RT)} running)</b>\n\n" + "\n\n".join(out))


def _panel_action(kind):
    async def h(message: Message, command: CommandObject):
        d = await find_clone(0, command.args, any_owner=True)
        if not d:
            return await message.answer(f"Usage: <code>/{kind}clone @botusername</code>")
        bid = d["bot_id"]
        if kind == "disable":
            await db.clones.update_one({"bot_id": bid}, {"$set": {"enabled": False}})
            await stop_clone(bid)
            await message.answer(f"⛔ @{esc(d['username'])} disabled.")
        elif kind == "enable":
            await db.clones.update_one({"bot_id": bid}, {"$set": {"enabled": True}})
            d["enabled"] = True
            err = await start_clone(d) if d.get("active", True) else None
            await message.answer(f"✅ @{esc(d['username'])} enabled." + (f"\n⚠️ {esc(err)}" if err else ""))
        else:
            await stop_clone(bid)
            await delete_clone_data(bid)
            await message.answer(f"🗑 @{esc(d['username'])} disconnected & deleted.")
    return h


for _k in ("disable", "enable", "del"):
    _REG.append(("message", (Command(f"{_k}clone"), MasterSudo()), _panel_action(_k)))


# ═══════════════════════════ COMMAND MENUS ═══════════════════════════
USER_CMDS = [("start", "Start the bot"), ("help", "Commands guide"), ("settings", "Group settings"), ("all", "Tag everyone"), ("admins", "Tag admins"),
             ("anybody", "Tag a random member"), ("gmtag", "Good morning tag"), ("gntag", "Good night tag"), ("vctag", "VC invite tag"),
             ("tagall", "Fun tag, one by one"), ("stop", "Stop tagging"), ("unreg", "Leave tag list"), ("reg", "Join tag list again"),
             ("id", "Show your ID"), ("optout", "Stop DM broadcasts")]
CLONE_CMDS = [("clone", "Create your own bot"), ("myclones", "Your clones")]
OWNER_CMDS = [("stats", "Bot stats"), ("broadcast", "Broadcast to users"), ("gcast", "Broadcast to groups"), ("bclog", "Last broadcast report"),
              ("ban", "Ban user/group"), ("unban", "Unban"), ("groups", "List groups"), ("ping", "Check speed"),
              ("setsupport", "Set support button"), ("delsupport", "Delete support button"), ("supports", "List buttons"), ("setowner", "Set owner button")]
MASTER_CMDS = [("ucast", "Broadcast to clone users"), ("clonelist", "All clones"), ("disableclone", "Disable a clone"), ("enableclone", "Enable a clone"), ("delclone", "Delete a clone")]
SUPER_CMDS = [("addsudo", "Add sudo"), ("delsudo", "Remove sudo"), ("sudolist", "List sudo"), ("restart", "Restart bot")]


async def setup_menus(bot):
    master = is_master(bot)
    base = USER_CMDS + (CLONE_CMDS if master else [])
    with contextlib.suppress(TelegramAPIError):
        await bot.set_my_commands([BotCommand(command=a, description=b) for a, b in base], scope=BotCommandScopeDefault())
    owners = {CTX[bot.id]["owner_id"]} | ({OWNER_ID} | SUDO if master else set())
    for uid in owners:
        cmds = base + OWNER_CMDS + (MASTER_CMDS if master else []) + (SUPER_CMDS if master and uid == OWNER_ID else [])
        with contextlib.suppress(TelegramAPIError):
            await bot.set_my_commands([BotCommand(command=a, description=b) for a, b in cmds], scope=BotCommandScopeChat(chat_id=uid))


# ═══════════════════════════ RUN ═══════════════════════════
async def boot_clones():
    async for doc in db.clones.find({"enabled": True, "active": True}):
        err = await start_clone(doc)
        if err:
            log.warning("clone %s not started: %s", doc.get("username"), err)
        await asyncio.sleep(0.5)


async def main():
    global MASTER, MASTER_UN
    await init_db()
    MASTER = Bot(BOT_TOKEN, default=DEFAULT)
    me = await MASTER.get_me()
    MASTER_UN = me.username
    CTX[me.id] = {"master": True, "owner_id": OWNER_ID, "username": me.username}
    await db.tag_sessions.update_many({"status": "running"}, {"$set": {"status": "interrupted"}})  # no duplicate resume after restart
    dp = build_dispatcher()
    await setup_menus(MASTER)
    asyncio.create_task(boot_clones())
    log.info("⚡ Kuku Tag Bot v3 started as @%s", me.username)
    await send_log(f"✅ <b>Bot started</b> • @{me.username} • {now_str()}")
    try:
        await dp.start_polling(MASTER)
    finally:
        for bid in list(RT):
            await stop_clone(bid)
        await MASTER.session.close()


if __name__ == "__main__":
    asyncio.run(main())

"""⚡ 𝕂𝕦𝕜𝕦 Tag Bot - single file edition (no folders)."""
import asyncio
import html
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.enums import ChatMemberStatus, ChatMembersFilter, ChatType, ParseMode, UserStatus
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import (
    BotCommand, BotCommandScopeChat, BotCommandScopeDefault,
    InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("kuku")
HTML = ParseMode.HTML
START_TIME = time.time()

# ══════════════════════════ CONFIG ══════════════════════════
def _req(k):
    v = os.getenv(k)
    if not v:
        raise SystemExit(f"❌ Missing environment variable: {k}")
    return v


def _first(*keys):
    for k in keys:
        if os.getenv(k):
            return os.getenv(k)
    return None


API_ID = int(_req("API_ID"))
API_HASH = _req("API_HASH")
BOT_TOKEN = _req("BOT_TOKEN")
OWNER_ID = int(_req("OWNER_ID"))
MONGO_URL = _first("MONGO_URL", "MONGO_DB_URI", "MONGODB_URL", "MONGO_URI")
if not MONGO_URL:
    raise SystemExit("❌ Missing environment variable: MONGO_URL")
DB_NAME = os.getenv("DB_NAME", "kukudb")
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0") or 0)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
app = Client("kuku", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

# ══════════════════════════ FONTS & THEMES ══════════════════════════
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
    "bold": _mk(0x1D5D4, 0x1D5EE),
    "italic": _mk(0x1D63C, 0x1D656),
    "script": _mk(0x1D4D0, 0x1D4EA),
    "double": _mk(0x1D538, 0x1D552, {"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"}),
    "small": _SM,
}
_TABLES = {k: str.maketrans(v) for k, v in _MAPS.items()}
_TOKEN = re.compile(r"(<[^>]*>|&#?\w+;)")
_SKIP = {"a", "code", "pre"}
_TAGN = re.compile(r"<(/?)(\w+)")


def f(text, font):
    t = _TABLES.get(font)
    return text.translate(t) if t else text


def f_html(h, font):
    """Font on normal text only - links, code and premium emoji stay untouched."""
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


# ══════════════════════════ DATABASE ══════════════════════════
db = None
DEFAULTS = dict(style="mention", per=5, limit=0, font="bold", theme="neon", who_all="staff", who_tagall="staff", welcome=True, left=True)
_cache, _groups, _users, _sudo = {}, set(), set(), set()
_bans = None


async def get_chat(cid):
    if cid in _cache:
        return _cache[cid]
    doc = await db.groups.find_one({"_id": cid}) or {}
    cfg = {**DEFAULTS, **{k: v for k, v in doc.items() if k in DEFAULTS}}
    _cache[cid] = cfg
    return cfg


async def set_chat(cid, key, val):
    cfg = await get_chat(cid)
    cfg[key] = val
    await db.groups.update_one({"_id": cid}, {"$set": {key: val}}, upsert=True)


async def add_group(cid, title):
    """True only the first time this group is ever seen."""
    if cid in _groups:
        return False
    _groups.add(cid)
    r = await db.groups.update_one({"_id": cid}, {"$set": {"title": title}}, upsert=True)
    return r.upserted_id is not None


async def add_user(uid):
    if uid in _users:
        return False
    _users.add(uid)
    r = await db.users.update_one({"_id": uid}, {"$set": {"ok": True}}, upsert=True)
    return r.upserted_id is not None


async def unreg_set(cid):
    d = await db.unreg.find_one({"_id": cid})
    return set(d.get("users", [])) if d else set()


async def get_meta(key, default=None):
    d = await db.meta.find_one({"_id": key})
    return d["v"] if d and "v" in d else default


async def set_meta(key, v):
    await db.meta.update_one({"_id": key}, {"$set": {"v": v}}, upsert=True)


async def _load_bans():
    global _bans
    if _bans is None:
        _bans = {d["_id"] async for d in db.bans.find()}


async def is_banned(i):
    await _load_bans()
    return i in _bans


async def is_sudo(uid):
    return uid == OWNER_ID or uid in _sudo


async def all_targets(kind="all"):
    ids = []
    if kind in ("all", "users"):
        ids += [d["_id"] async for d in db.users.find()]
    if kind in ("all", "groups"):
        ids += [d["_id"] async for d in db.groups.find()]
    return ids


# ══════════════════════════ HELPERS ══════════════════════════
_me = None


async def get_me():
    global _me
    if _me is None:
        _me = await app.get_me()
    return _me


def now_ist():
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %I:%M %p") + " IST"


def ulink(u):
    return f'<a href="tg://user?id={u.id}">{html.escape(u.first_name or "User")}</a>'


async def send_log(text):
    if not LOG_GROUP_ID:
        return
    try:
        await app.send_message(LOG_GROUP_ID, text, parse_mode=HTML, disable_web_page_preview=True)
    except Exception as e:
        log.warning("log send failed: %s", e)


async def is_admin(chat_id, uid):
    if await is_sudo(uid):
        return True
    try:
        m = await app.get_chat_member(chat_id, uid)
    except Exception:
        return False
    return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


async def can_use(message, level):
    uid = message.from_user.id if message.from_user else None
    if uid is not None and await is_sudo(uid) and level != "botowner":
        return True
    if uid == OWNER_ID:
        return True
    if level == "all":
        return True
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return level == "staff"
    if uid is None or level == "botowner":
        return False
    try:
        m = await app.get_chat_member(message.chat.id, uid)
    except Exception:
        return False
    if level == "owner":
        return m.status == ChatMemberStatus.OWNER
    return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


async def fetch_members(chat_id, admins_only=False):
    out = []
    kw = {"filter": ChatMembersFilter.ADMINISTRATORS} if admins_only else {}
    try:
        async for m in app.get_chat_members(chat_id, **kw):
            u = m.user
            if u and not u.is_bot and not u.is_deleted:
                out.append(u)
    except Exception as e:
        log.warning("fetch_members failed: %s", e)
    return out


_RANK = {UserStatus.ONLINE: 0, UserStatus.RECENTLY: 1, UserStatus.LAST_WEEK: 2, UserStatus.LAST_MONTH: 3, UserStatus.LONG_AGO: 4}
EMOJIS = list("😀😎🥳🤩😍🔥⚡💫✨🌸🍀🦋🌈💎👑🎯🚀🎉💖🌟🍕🎧🐱🦁🐯🦄🌙☀️🍭")


def mention(u, style):
    name = html.escape((u.first_name or "User")[:25])
    if style == "emoji":
        return f'<a href="tg://user?id={u.id}">{random.choice(EMOJIS)}</a>'
    if style == "username" and u.username:
        return f"@{u.username}"
    if style == "plain":
        return f"<b>{name}</b>"
    return f'<a href="tg://user?id={u.id}">{name}</a>'


_PREFIX = re.compile(r"(?is)^\s*(/\w+(@\w+)?|@all|all|@admins?)(\s+|$)")


def extract_text(message):
    src = message.text or message.caption
    return _PREFIX.sub("", src.html, count=1).strip() if src else ""


async def banned(message):
    if await is_banned(message.chat.id):
        return True
    return bool(message.from_user and await is_banned(message.from_user.id))


def norm_url(s):
    s = s.strip()
    if s.startswith("@"):
        return "https://t.me/" + s[1:]
    if s.isdigit():
        return f"tg://user?id={s}"
    if s.startswith(("http://", "https://", "tg://")):
        return s
    if s.startswith(("t.me/", "telegram.me/")):
        return "https://" + s
    return None


async def photo_of(chat_id):
    try:
        chat = await app.get_chat(chat_id)
        if chat.photo:
            return await app.download_media(chat.photo.big_file_id, in_memory=True)
    except Exception as e:
        log.info("no photo for %s: %s", chat_id, e)
    return None


# ══════════════════════════ FILTERS ══════════════════════════
async def _owner_f(_, __, m):
    return bool(m.from_user and m.from_user.id == OWNER_ID)


async def _sudo_f(_, __, m):
    return bool(m.from_user and await is_sudo(m.from_user.id))


OWNER = filters.create(_owner_f)
SUDO = filters.create(_sudo_f)

# ══════════════════════════ START / HELP ══════════════════════════
def home_caption(u):
    body = (
        f"👋 {S('hello')} {ulink(u)}\n"
        f"🆔 {S('id')}  ›  <code>{u.id}</code>\n\n"
        f"✨ <b>{S('premium tagging bot for telegram')}</b>\n"
        f"💠 {S('tag everyone in style')}\n"
        f"💠 {S('fonts, themes and emoji styles')}\n"
        f"💠 {S('welcome with group dp')}\n\n"
        f"🛡 {S('add me to your group and make me admin')}"
    )
    return wrap("neon", S("kuku"), body)


async def home_markup():
    me = await get_me()
    rows = [[Btn("➕ Add Me To Group", url=f"https://t.me/{me.username}?startgroup=true&admin=invite_users+delete_messages")]]
    own = await get_meta("owner") or {"url": f"tg://user?id={OWNER_ID}", "name": "👑 Owner"}
    rows.append([Btn("📖 Guide", callback_data="hp:help"), Btn(own["name"], url=own["url"])])
    sup = await get_meta("supports", {})
    btns = [Btn(v["name"], url=v["url"]) for k, v in sorted(sup.items(), key=lambda x: int(x[0]))]
    rows += [btns[i:i + 2] for i in range(0, len(btns), 2)]
    return Kb(rows)


async def send_home(chat_id, user):
    cap, kb = home_caption(user), await home_markup()
    photo = await photo_of(user.id)
    if photo:
        photo.seek(0)
        try:
            return await app.send_photo(chat_id, photo, caption=cap, reply_markup=kb, parse_mode=HTML)
        except Exception as e:
            log.warning("send_photo failed: %s", e)
    await app.send_message(chat_id, cap, reply_markup=kb, parse_mode=HTML)


def help_text(sudo, owner):
    t = (
        "🏷 <b>Tagging</b> <i>(admins)</i>\n"
        "• /all [text] • all • @all\n• /admins [text] • @admin\n"
        "• /anybody • /gmtag • /gntag • /vctag\n• /tagall [text] — one by one fun tag\n• /stop — stop tagging\n\n"
        "⚙️ <b>Group</b>\n• /settings • /unreg • /reg • /id"
    )
    if sudo:
        t += ("\n\n👑 <b>Owner / Sudo</b>\n• /stats • /broadcast • /gcast • /ucast\n• /ban • /unban • /groups • /ping • /restart\n"
              "• /setsupport [n] link name • /delsupport n • /supports\n• /setowner link name")
    if owner:
        t += "\n• /addsudo • /delsudo • /sudolist"
    return wrap("neon", S("guide"), t)


@app.on_message(filters.command("start"))
async def start_cmd(c, m):
    if await banned(m):
        return
    u = m.from_user
    if m.chat.type == ChatType.PRIVATE and u:
        if await add_user(u.id):
            total = len(await all_targets("users"))
            await send_log(
                f"👤 <b>New User Started Bot</b>\n\n"
                f"• Name: {ulink(u)}\n• Username: {'@' + u.username if u.username else 'None'}\n"
                f"• ID: <code>{u.id}</code>\n• Time: {now_ist()}\n• Total users: <b>{total}</b>"
            )
        await send_home(m.chat.id, u)
    elif u:
        await add_group(m.chat.id, m.chat.title or "")
        await m.reply_text(home_caption(u), reply_markup=await home_markup(), parse_mode=HTML)


@app.on_message(filters.command("help"))
async def help_cmd(c, m):
    uid = m.from_user.id if m.from_user else 0
    await m.reply_text(help_text(await is_sudo(uid), uid == OWNER_ID), parse_mode=HTML)


@app.on_callback_query(filters.regex(r"^hp:"))
async def help_cb(c, q):
    msg, uid = q.message, q.from_user.id
    if q.data == "hp:help":
        text = help_text(await is_sudo(uid), uid == OWNER_ID)
        kb = Kb([[Btn("⬅️ Back", callback_data="hp:back")]])
        try:
            if msg.photo and len(text) <= 1000:
                await msg.edit_caption(text, reply_markup=kb, parse_mode=HTML)
            elif msg.photo:
                await msg.delete()
                await c.send_message(msg.chat.id, text, reply_markup=kb, parse_mode=HTML)
            else:
                await msg.edit_text(text, reply_markup=kb, parse_mode=HTML)
        except MessageNotModified:
            pass
    else:
        try:
            await msg.delete()
        except Exception:
            pass
        await send_home(msg.chat.id, q.from_user)
    await q.answer()


@app.on_message(filters.command("id"))
async def id_cmd(c, m):
    uid = m.from_user.id if m.from_user else "anonymous"
    await m.reply_text(f"🆔 Your ID: <code>{uid}</code>\n💬 Chat ID: <code>{m.chat.id}</code>", parse_mode=HTML)


@app.on_message(filters.group & filters.command("unreg"))
async def unreg_cmd(c, m):
    if m.from_user:
        await db.unreg.update_one({"_id": m.chat.id}, {"$addToSet": {"users": m.from_user.id}}, upsert=True)
        await m.reply_text("✅ Ab aap tag list se bahar ho. Wapas aane ke liye /reg")


@app.on_message(filters.group & filters.command("reg"))
async def reg_cmd(c, m):
    if m.from_user:
        await db.unreg.update_one({"_id": m.chat.id}, {"$pull": {"users": m.from_user.id}}, upsert=True)
        await m.reply_text("✅ Aap wapas tag list me aa gaye.")


# ══════════════════════════ TAGGING ══════════════════════════
RUN = {}
TITLES = {"all": "TAG ALL", "admins": "CALLING ADMINS", "anybody": "LUCKY ONE", "gmtag": "GOOD MORNING", "gntag": "GOOD NIGHT", "vctag": "VC INVITE", "tagall": "TAG ALL • FUN"}
GM = ["Good Morning ji! ☀️ Uth jao, chai thandi ho rahi hai ☕", "Subah ho gayi mamu! 🌅 Ab to aankhein khol lo 😄",
      "Good Morning! 🌸 Aaj ka din tumhare naam ✨", "Rise & Shine 🌞 Phone chhodo, muh dhoo lo 😂",
      "Suprabhat 🙏 Aaj kuch accha karna hai, sirf scroll nahi 😎", "Good Morning 💫 Smile karo, aaj din mast jayega 😊"]
GN = ["Good Night 🌙 Phone rakho aur so jao 😴", "Shubh Ratri ✨ Sapno me milte hain 💤", "Good Night 🌌 Kal phir se masti karenge 😄",
      "Raat bahut ho gayi 🌃 Ab so jao, kal exam nahi to bhi 😂", "Sweet Dreams 💖 Subah milte hain, bye 👋", "Good Night 🌙 Charging pe laga do khud ko 🔋"]
VC = ["VC me aao sab log! 🎙️ Maza aayega 🔥", "Voice chat chalu hai 🎧 Jaldi join karo!", "Sab VC me aa jao yaar, akela bore ho raha hu 😭🎙️", "Mic ready karo 🎤 VC me party chal rahi hai 🥳"]
FUNNY = ["Oye! Kidhar ho? Group me aao 😂", "Tumhe dhundh dhundh ke thak gaya hu 🥲", "Bhai/Behen, zinda ho? Reply to karo 😆",
         "Ek message ka sawaab hai, chhupo mat 😎", "Aaj tumhari baari hai, bach ke kahan jaoge 😜", "Phone ka network theek hai? Group me aa jao 🤣",
         "Tumhare bina group adhura hai 🥺💖", "Hello hello? Mic check 1 2 3 🎤😂", "Online ho ya sirf last seen chhupa rakha hai? 🕵️", "Chai pee ke aa jao, hum wait kar rahe hain ☕😄"]
POOL = {"gmtag": GM, "gntag": GN, "vctag": VC, "tagall": FUNNY}


def tg_kb(paused):
    first = Btn("▶️ Resume", callback_data="tg:resume") if paused else Btn("⏸ Pause", callback_data="tg:pause")
    return Kb([[first, Btn("⛔ Stop", callback_data="tg:stop")]])


def progress(done, total, state):
    n = int(10 * done / total) if total else 0
    return f"💠 <b>{S('tagging')}</b> • {state}\n<code>{'▰' * n}{'▱' * (10 - n)}</code>  <b>{done}/{total}</b>"


def build(cfg, mode, text_fn, batch):
    style, theme, font = cfg["style"], cfg["theme"], cfg["font"]
    ments = [mention(u, style) for u in batch]
    mline = " ".join(ments) if style == "emoji" else "\n".join(f"{BULLET.get(theme, '•')} {x}" for x in ments)
    text = text_fn()
    body = (f_html(text, font) + "\n\n" if text else "") + mline
    return wrap(theme, f(TITLES[mode], font), body)


async def send_split(chat_id, batch, cfg, mode, text_fn):
    msg = build(cfg, mode, text_fn, batch)
    if len(msg) > 3900 and len(batch) > 1:
        h = len(batch) // 2
        await send_split(chat_id, batch[:h], cfg, mode, text_fn)
        await send_split(chat_id, batch[h:], cfg, mode, text_fn)
        return
    while True:
        try:
            await app.send_message(chat_id, msg, parse_mode=HTML, disable_web_page_preview=True)
            return
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)


async def run_tag(message, members, cfg, mode, text_fn):
    chat_id = message.chat.id
    uid = message.from_user.id if message.from_user else 0
    total = len(members)
    if not total:
        await message.reply_text("⚠️ Koi member nahi mila. Mujhe <b>admin</b> banao taaki main members dekh sakun.", parse_mode=HTML)
        return
    separate = mode == "tagall"
    per = 1 if separate else int(cfg["per"])
    st = {"stop": False, "paused": False, "go": asyncio.Event(), "by": uid}
    st["go"].set()
    RUN[chat_id] = st
    ctl = await message.reply_text(progress(0, total, "▶️ running"), reply_markup=tg_kb(False), parse_mode=HTML)
    done, err = 0, None
    try:
        for i in range(0, total, per):
            await st["go"].wait()
            if st["stop"]:
                break
            batch = members[i:i + per]
            await send_split(chat_id, batch, cfg, mode, text_fn)
            done += len(batch)
            try:
                await ctl.edit_text(progress(done, total, "⏸ paused" if st["paused"] else "▶️ running"), reply_markup=tg_kb(st["paused"]), parse_mode=HTML)
            except Exception:
                pass
            await asyncio.sleep(3 if separate else 2.5)
    except Exception as e:
        err = str(e)
        log.warning("tagging error: %s", e)
        await send_log(f"⚠️ <b>Tag error</b>\n🏠 {html.escape(message.chat.title or '')}\n🆔 <code>{chat_id}</code>\n<code>{html.escape(err[:200])}</code>")
    finally:
        RUN.pop(chat_id, None)
    if err:
        end = f"⚠️ <b>{S('error')}</b>: <code>{html.escape(err[:100])}</code>"
    elif st["stop"]:
        end = f"⛔ <b>{S('stopped')}</b> • {done}/{total}"
    else:
        end = f"✅ <b>{S('completed')}</b> • {done}/{total}"
    try:
        await ctl.edit_text(end, parse_mode=HTML)
    except Exception:
        pass


async def start_tag(message, mode, silent=False):
    chat_id = message.chat.id
    if await banned(message):
        return
    cfg = await get_chat(chat_id)
    level = cfg["who_tagall"] if mode == "tagall" else cfg["who_all"]
    if not await can_use(message, level):
        if not silent:
            names = {"staff": "admins", "owner": "group owner", "botowner": "bot owner"}
            await message.reply_text(f"⛔ Ye command sirf <b>{names.get(level, 'allowed users')}</b> use kar sakte hain.", parse_mode=HTML)
        return
    if chat_id in RUN:
        if not silent:
            await message.reply_text("⏳ Tagging pehle se chal rahi hai. Rokne ke liye /stop.")
        return
    await add_group(chat_id, message.chat.title or "")
    custom = extract_text(message)
    members = await fetch_members(chat_id, admins_only=(mode == "admins"))
    unreg = await unreg_set(chat_id)
    members = [u for u in members if u.id not in unreg]
    if mode == "vctag":
        members.sort(key=lambda u: _RANK.get(u.status, 5))
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
    await run_tag(message, members, cfg, mode, text_fn)


def _mk_cmd(mode):
    async def h(c, m):
        await start_tag(m, mode)
    return h


for _mode in ("all", "admins", "anybody", "gmtag", "gntag", "vctag", "tagall"):
    app.on_message(filters.group & filters.command(_mode))(_mk_cmd(_mode))


@app.on_message(filters.group & filters.regex(r"(?i)^(@all|all)(\s|$)"))
async def p_all(c, m):
    await start_tag(m, "all", silent=True)


@app.on_message(filters.group & filters.regex(r"(?i)^@admins?(\s|$)"))
async def p_admin(c, m):
    await start_tag(m, "admins", silent=True)


@app.on_message(filters.group & filters.command("stop"))
async def stop_cmd(c, m):
    st = RUN.get(m.chat.id)
    if not st:
        return await m.reply_text("ℹ️ Abhi koi tagging nahi chal rahi.")
    uid = m.from_user.id if m.from_user else 0
    if uid != st["by"] and not await can_use(m, "staff"):
        return await m.reply_text("⛔ Sirf admins ya tagging shuru karne wala rok sakta hai.")
    st["stop"] = True
    st["go"].set()
    await m.reply_text("⛔ Tagging rok di gayi.")


@app.on_callback_query(filters.regex(r"^tg:(pause|resume|stop)$"))
async def tg_cb(c, q):
    chat_id = q.message.chat.id
    st = RUN.get(chat_id)
    if not st:
        return await q.answer("Tagging chal nahi rahi.", show_alert=True)
    if q.from_user.id != st["by"] and not await is_admin(chat_id, q.from_user.id):
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
    try:
        await q.message.edit_reply_markup(tg_kb(st["paused"]))
    except Exception:
        pass


# ══════════════════════════ SETTINGS ══════════════════════════
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
    for v, lab in SCHEMA[key][1]:
        if v == str(val):
            return lab
    return str(val)


def main_text(cfg):
    onoff = lambda v: "ON" if v else "OFF"  # noqa: E731
    rows = [
        f"🎨 {S('style')}  ›  <b>{label('style', cfg['style'])}</b>",
        f"📦 {S('per message')}  ›  <b>{cfg['per']}</b>",
        f"🎯 {S('limit')}  ›  <b>{label('limit', cfg['limit'])}</b>",
        f"🔠 {S('font')}  ›  <b>{label('font', cfg['font'])}</b>",
        f"🌈 {S('theme')}  ›  <b>{label('theme', cfg['theme'])}</b>",
        f"👑 /all  ›  <b>{label('who_all', cfg['who_all'])}</b>",
        f"😂 /tagall  ›  <b>{label('who_tagall', cfg['who_tagall'])}</b>",
        f"👋 {S('welcome')}  ›  <b>{onoff(cfg['welcome'])}</b>   🚪 {S('left')}  ›  <b>{onoff(cfg['left'])}</b>",
    ]
    return wrap("neon", S("kuku settings"), "\n".join(rows))


def kb_main(cfg):
    dot = lambda v: "🟢" if v else "🔴"  # noqa: E731
    return Kb([
        [Btn("🎨 Style", callback_data="st:menu:style"), Btn("📦 Per Msg", callback_data="st:menu:per")],
        [Btn("🎯 Limit", callback_data="st:menu:limit"), Btn("🔠 Font", callback_data="st:menu:font")],
        [Btn("🌈 Theme", callback_data="st:menu:theme"), Btn("👑 /all Access", callback_data="st:menu:who_all")],
        [Btn("😂 /tagall Access", callback_data="st:menu:who_tagall")],
        [Btn(f"{dot(cfg['welcome'])} Welcome", callback_data="st:tog:welcome"), Btn(f"{dot(cfg['left'])} Left", callback_data="st:tog:left")],
        [Btn("✖️ Close", callback_data="st:close")],
    ])


def kb_menu(cfg, key):
    cur = str(cfg[key])
    btns = [Btn(("✅ " if v == cur else "") + lab, callback_data=f"st:set:{key}:{v}") for v, lab in SCHEMA[key][1]]
    cols = 4 if key == "per" else 3 if key == "limit" else 2
    rows = [btns[i:i + cols] for i in range(0, len(btns), cols)]
    rows.append([Btn("⬅️ Back", callback_data="st:main")])
    return Kb(rows)


async def show(q, text, markup):
    try:
        await q.message.edit_text(text, reply_markup=markup, parse_mode=HTML)
    except MessageNotModified:
        pass


@app.on_message(filters.command("settings"))
async def settings_cmd(c, m):
    if m.chat.type == ChatType.PRIVATE:
        return await m.reply_text("⚙️ Settings group me kholo (mujhe admin banake <code>/settings</code> likho).", parse_mode=HTML)
    if not await can_use(m, "staff"):
        return await m.reply_text("⛔ Settings sirf admins badal sakte hain.")
    await add_group(m.chat.id, m.chat.title or "")
    cfg = await get_chat(m.chat.id)
    await m.reply_text(main_text(cfg), reply_markup=kb_main(cfg), parse_mode=HTML)


@app.on_callback_query(filters.regex(r"^st:"))
async def settings_cb(c, q):
    chat_id = q.message.chat.id
    if not await is_admin(chat_id, q.from_user.id):
        return await q.answer("🛡 Sirf admins settings badal sakte hain.", show_alert=True)
    parts = q.data.split(":")
    act = parts[1]
    cfg = await get_chat(chat_id)
    if act == "close":
        await q.message.delete()
        return
    if act == "main":
        await show(q, main_text(cfg), kb_main(cfg))
    elif act == "menu":
        key = parts[2]
        await show(q, wrap("neon", S(SCHEMA[key][0].split(" ", 1)[1]), f"{SCHEMA[key][0]}\n\n👇 {S('select an option')}"), kb_menu(cfg, key))
    elif act == "set":
        key, val = parts[2], parts[3]
        await set_chat(chat_id, key, int(val) if key in ("per", "limit") else val)
        cfg = await get_chat(chat_id)
        await show(q, wrap("neon", S(SCHEMA[key][0].split(" ", 1)[1]), f"✅ {S('saved')}: <b>{label(key, val)}</b>"), kb_menu(cfg, key))
        return await q.answer("✅ Saved")
    elif act == "tog":
        key = parts[2]
        await set_chat(chat_id, key, not cfg[key])
        cfg = await get_chat(chat_id)
        await show(q, main_text(cfg), kb_main(cfg))
    await q.answer()


# ══════════════════════════ WELCOME / LEFT + LOGS ══════════════════════════
@app.on_message(filters.group & filters.new_chat_members, group=2)
async def welcome(c, m):
    chat = m.chat
    cfg = await get_chat(chat.id)
    title = html.escape(chat.title or "Group")
    for u in m.new_chat_members:
        try:
            if u.is_self:
                new = await add_group(chat.id, chat.title or "")
                try:
                    count = await c.get_chat_members_count(chat.id)
                except Exception:
                    count = "?"
                adder = m.from_user
                total = len(await all_targets("groups"))
                await send_log(
                    f"➕ <b>Bot Added To Group</b>\n\n• Group: <b>{title}</b>\n• ID: <code>{chat.id}</code>\n"
                    f"• Username: {'@' + chat.username if chat.username else 'Private'}\n• Members: <b>{count}</b>\n"
                    f"• Added by: {ulink(adder) if adder else 'Unknown'}"
                    + (f"\n• Adder username: @{adder.username}" if adder and adder.username else "")
                    + (f"\n• Adder ID: <code>{adder.id}</code>" if adder else "")
                    + f"\n• Time: {now_ist()}\n• Total groups: <b>{total}</b>"
                )
                await c.send_message(chat.id, wrap("neon", S("thanks for adding me"),
                    f"⚡ <b>{S('kuku tag bot')}</b> {S('is ready')}!\n\n🛡 {S('make me admin to tag everyone')}\n⚙️ /settings  •  📖 /start"), parse_mode=HTML)
                continue
            if u.is_bot or not cfg["welcome"]:
                continue
            try:
                count = await c.get_chat_members_count(chat.id)
            except Exception:
                count = "?"
            body = (f"👤 {S('name')}  ›  {ulink(u)}\n🆔 {S('id')}  ›  <code>{u.id}</code>\n"
                    f"🔗 {S('username')}  ›  {'@' + u.username if u.username else S('none')}\n"
                    f"🏠 {S('group')}  ›  <b>{title}</b>\n👥 {S('members')}  ›  <b>{count}</b>")
            cap = wrap("neon", S("welcome"), body)
            photo = await photo_of(chat.id)
            if photo:
                photo.seek(0)
                await c.send_photo(chat.id, photo, caption=cap, parse_mode=HTML)
            else:
                await c.send_message(chat.id, cap, parse_mode=HTML)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            log.warning("welcome error: %s", e)


@app.on_message(filters.group & filters.left_chat_member, group=2)
async def left(c, m):
    u = m.left_chat_member
    if not u:
        return
    if u.is_self:
        by = m.from_user
        await send_log(f"➖ <b>Bot Removed From Group</b>\n\n• Group: <b>{html.escape(m.chat.title or '')}</b>\n• ID: <code>{m.chat.id}</code>\n"
                       f"• Removed by: {ulink(by) if by else 'Unknown'}\n• Time: {now_ist()}")
        return
    if u.is_bot or not (await get_chat(m.chat.id))["left"]:
        return
    text = wrap("neon", S("goodbye"), f"👋 {ulink(u)} {S('left the group')} 😢\n💔 {S('bye bye, take care')} ✨")
    try:
        await c.send_message(m.chat.id, text, parse_mode=HTML)
    except Exception as e:
        log.warning("left msg error: %s", e)


# ══════════════════════════ OWNER / SUDO COMMANDS ══════════════════════════
@app.on_message(filters.command("ping") & SUDO)
async def ping_cmd(c, m):
    t = time.time()
    r = await m.reply_text("🏓 ...")
    await r.edit_text(f"🏓 <b>Pong!</b> <code>{int((time.time() - t) * 1000)} ms</code>", parse_mode=HTML)


@app.on_message(filters.command("stats") & SUDO)
async def stats_cmd(c, m):
    await _load_bans()
    up = int(time.time() - START_TIME)
    d, r = divmod(up, 86400)
    h, r = divmod(r, 3600)
    body = (f"👤 {S('users')}  ›  <b>{len(await all_targets('users'))}</b>\n👥 {S('groups')}  ›  <b>{len(await all_targets('groups'))}</b>\n"
            f"🚫 {S('banned')}  ›  <b>{len(_bans)}</b>\n🛡 {S('sudo')}  ›  <b>{len(_sudo)}</b>\n"
            f"🏷 {S('active tagging')}  ›  <b>{len(RUN)}</b>\n⏱ {S('uptime')}  ›  <b>{d}d {h}h {r // 60}m</b>")
    await m.reply_text(wrap("neon", S("bot stats"), body), parse_mode=HTML)


async def _bcast(m, kind):
    reply = m.reply_to_message
    parts = m.text.split(None, 1)
    text = parts[1] if len(parts) > 1 else None
    if not reply and not text:
        return await m.reply_text("Usage: <code>/broadcast message</code> (ya kisi message par reply karo)", parse_mode=HTML)
    targets = await all_targets(kind)
    note = await m.reply_text(f"📣 Broadcast shuru... {len(targets)} chats")
    ok = fail = 0
    for cid in targets:
        for _ in range(2):
            try:
                if reply:
                    await reply.copy(cid)
                else:
                    await app.send_message(cid, text)
                ok += 1
                break
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception:
                fail += 1
                break
        await asyncio.sleep(0.1)
    await note.edit_text(f"✅ Broadcast done\n\n📬 Sent: {ok}\n❌ Failed: {fail}")


@app.on_message(filters.command("broadcast") & SUDO)
async def bc_all(c, m):
    await _bcast(m, "all")


@app.on_message(filters.command("gcast") & SUDO)
async def bc_groups(c, m):
    await _bcast(m, "groups")


@app.on_message(filters.command("ucast") & SUDO)
async def bc_users(c, m):
    await _bcast(m, "users")


async def _id_arg(m):
    parts = m.text.split()
    if m.reply_to_message and m.reply_to_message.from_user and len(parts) < 2:
        return m.reply_to_message.from_user.id
    if len(parts) < 2:
        await m.reply_text("Usage: <code>/ban user_or_group_id</code>", parse_mode=HTML)
        return None
    try:
        return int(parts[1])
    except ValueError:
        await m.reply_text("❌ ID number honi chahiye.")
        return None


@app.on_message(filters.command("ban") & SUDO)
async def ban_cmd(c, m):
    i = await _id_arg(m)
    if i is None:
        return
    if i == OWNER_ID:
        return await m.reply_text("😅 Owner ko ban nahi kar sakte.")
    await _load_bans()
    _bans.add(i)
    await db.bans.update_one({"_id": i}, {"$set": {"ok": True}}, upsert=True)
    await m.reply_text(f"🚫 Banned: <code>{i}</code>", parse_mode=HTML)


@app.on_message(filters.command("unban") & SUDO)
async def unban_cmd(c, m):
    i = await _id_arg(m)
    if i is None:
        return
    await _load_bans()
    _bans.discard(i)
    await db.bans.delete_one({"_id": i})
    await m.reply_text(f"✅ Unbanned: <code>{i}</code>", parse_mode=HTML)


@app.on_message(filters.command("groups") & SUDO)
async def groups_cmd(c, m):
    docs = [d async for d in db.groups.find().limit(60)]
    if not docs:
        return await m.reply_text("Abhi koi group nahi.")
    lines = [f"{i}. {html.escape(str(d.get('title', '?')))[:30]} — <code>{d['_id']}</code>" for i, d in enumerate(docs, 1)]
    await m.reply_text("👥 <b>Groups</b>\n\n" + "\n".join(lines)[:3900], parse_mode=HTML)


@app.on_message(filters.command("restart") & OWNER)
async def restart_cmd(c, m):
    await m.reply_text("♻️ Restarting...")
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ---- support / owner buttons ----
@app.on_message(SUDO & filters.regex(r"^/setsupport(\d*)(@\w+)?(\s|$)"))
async def setsupport(c, m):
    num = re.match(r"^/setsupport(\d*)", m.text).group(1) or "1"
    parts = m.text.split(None, 2)
    if len(parts) < 2:
        return await m.reply_text(f"Usage: <code>/setsupport{'' if num == '1' else num} https://t.me/xyz Support Group</code>", parse_mode=HTML)
    url = norm_url(parts[1])
    if not url:
        return await m.reply_text("❌ Link galat hai. https://..., t.me/..., @username ya ID do.")
    name = parts[2].strip() if len(parts) > 2 else f"💬 Support {num}"
    sup = await get_meta("supports", {})
    sup[num] = {"url": url, "name": name[:40]}
    await set_meta("supports", sup)
    await m.reply_text(f"✅ Support button #{num} set:\n<b>{html.escape(name)}</b>\n{html.escape(url)}", parse_mode=HTML, disable_web_page_preview=True)


@app.on_message(filters.command("delsupport") & SUDO)
async def delsupport(c, m):
    parts = m.text.split()
    if len(parts) < 2:
        return await m.reply_text("Usage: <code>/delsupport 2</code>", parse_mode=HTML)
    sup = await get_meta("supports", {})
    if sup.pop(parts[1], None) is None:
        return await m.reply_text("❌ Ye number nahi mila. /supports dekho.")
    await set_meta("supports", sup)
    await m.reply_text(f"🗑 Support #{parts[1]} hata diya.")


@app.on_message(filters.command("supports") & SUDO)
async def supports_cmd(c, m):
    sup = await get_meta("supports", {})
    own = await get_meta("owner")
    lines = [f"#{k}  {html.escape(v['name'])} — {html.escape(v['url'])}" for k, v in sorted(sup.items(), key=lambda x: int(x[0]))]
    txt = "💬 <b>Support buttons</b>\n\n" + ("\n".join(lines) if lines else "Koi nahi.")
    txt += f"\n\n👑 <b>Owner button</b>\n{html.escape(own['name'] + ' — ' + own['url']) if own else 'Default (owner ID)'}"
    await m.reply_text(txt, parse_mode=HTML, disable_web_page_preview=True)


@app.on_message(filters.command("setowner") & SUDO)
async def setowner(c, m):
    parts = m.text.split(None, 2)
    if len(parts) < 2:
        return await m.reply_text("Usage: <code>/setowner @username Owner</code> (ya link / ID)", parse_mode=HTML)
    url = norm_url(parts[1])
    if not url:
        return await m.reply_text("❌ Link galat hai. @username, t.me/... ya ID do.")
    await set_meta("owner", {"url": url, "name": (parts[2].strip() if len(parts) > 2 else "👑 Owner")[:40]})
    await m.reply_text("✅ Owner button set ho gaya.")


# ---- sudo management (owner only) ----
async def set_menu_for(uid):
    cmds = USER_CMDS + SUDO_CMDS + (OWNER_CMDS if uid == OWNER_ID else [])
    try:
        await app.set_bot_commands([BotCommand(a, b) for a, b in cmds], scope=BotCommandScopeChat(uid))
    except Exception as e:
        log.info("menu for %s skipped: %s", uid, e)


@app.on_message(filters.command("addsudo") & OWNER)
async def addsudo(c, m):
    i = await _id_arg(m)
    if i is None:
        return
    _sudo.add(i)
    await db.sudo.update_one({"_id": i}, {"$set": {"ok": True}}, upsert=True)
    await set_menu_for(i)
    await m.reply_text(f"✅ Sudo added: <code>{i}</code>", parse_mode=HTML)


@app.on_message(filters.command("delsudo") & OWNER)
async def delsudo(c, m):
    i = await _id_arg(m)
    if i is None:
        return
    _sudo.discard(i)
    await db.sudo.delete_one({"_id": i})
    try:
        await app.delete_bot_commands(scope=BotCommandScopeChat(i))
    except Exception:
        pass
    await m.reply_text(f"🗑 Sudo removed: <code>{i}</code>", parse_mode=HTML)


@app.on_message(filters.command("sudolist") & OWNER)
async def sudolist(c, m):
    txt = "\n".join(f"• <code>{i}</code>" for i in sorted(_sudo)) or "Koi sudo nahi."
    await m.reply_text(f"🛡 <b>Sudo users</b>\n\n{txt}", parse_mode=HTML)


# ══════════════════════════ COMMAND MENUS ══════════════════════════
USER_CMDS = [("start", "Start the bot"), ("help", "Commands guide"), ("settings", "Group settings"), ("all", "Tag everyone"),
             ("admins", "Tag admins"), ("anybody", "Tag a random member"), ("gmtag", "Good morning tag"), ("gntag", "Good night tag"),
             ("vctag", "VC invite tag"), ("tagall", "Fun tag, one by one"), ("stop", "Stop tagging"), ("unreg", "Leave tag list"),
             ("reg", "Join tag list again"), ("id", "Show your ID")]
SUDO_CMDS = [("stats", "Bot stats"), ("broadcast", "Broadcast to all"), ("gcast", "Broadcast to groups"), ("ucast", "Broadcast to users"),
             ("ban", "Ban user/group"), ("unban", "Unban"), ("groups", "List groups"), ("ping", "Check bot speed"),
             ("setsupport", "Set support button"), ("delsupport", "Delete support button"), ("supports", "List buttons"), ("setowner", "Set owner button")]
OWNER_CMDS = [("addsudo", "Add sudo user"), ("delsudo", "Remove sudo user"), ("sudolist", "List sudo users"), ("restart", "Restart bot")]


async def set_menus():
    try:
        await app.set_bot_commands([BotCommand(a, b) for a, b in USER_CMDS], scope=BotCommandScopeDefault())
    except Exception as e:
        log.info("default menu skipped: %s", e)
    for uid in {OWNER_ID} | _sudo:
        await set_menu_for(uid)


# ══════════════════════════ RUN ══════════════════════════
async def main():
    global db
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    _sudo.update([d["_id"] async for d in db.sudo.find()])
    await app.start()
    me = await get_me()
    log.info("⚡ Kuku Tag Bot started as @%s", me.username)
    await set_menus()
    await send_log(f"✅ <b>Bot started</b> • @{me.username} • {now_ist()}")
    await idle()
    await app.stop()


if __name__ == "__main__":
    app.run(main())

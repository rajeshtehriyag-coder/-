"""All tagging commands: /all /admins /anybody /gmtag /gntag /vctag /tagall /stop + plain all/@all."""
import asyncio
import random

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from fonts import BULLET, S, f, f_html, wrap
from utils import banned, can_use, extract_text, fetch_members, is_admin, log, mention, status_rank

HTML = ParseMode.HTML
RUN: dict = {}  # chat_id -> state

TITLES = {
    "all": "TAG ALL", "admins": "CALLING ADMINS", "anybody": "LUCKY ONE",
    "gmtag": "GOOD MORNING", "gntag": "GOOD NIGHT", "vctag": "VC INVITE", "tagall": "TAG ALL • FUN",
}

GM = [
    "Good Morning ji! ☀️ Uth jao, chai thandi ho rahi hai ☕",
    "Subah ho gayi mamu! 🌅 Ab to aankhein khol lo 😄",
    "Good Morning! 🌸 Aaj ka din tumhare naam ✨",
    "Rise & Shine 🌞 Phone chhodo, muh dhoo lo 😂",
    "Suprabhat 🙏 Aaj kuch accha karna hai, sirf scroll nahi 😎",
    "Good Morning 💫 Smile karo, aaj din mast jayega 😊",
]
GN = [
    "Good Night 🌙 Phone rakho aur so jao 😴",
    "Shubh Ratri ✨ Sapno me milte hain 💤",
    "Good Night 🌌 Kal phir se masti karenge 😄",
    "Raat bahut ho gayi 🌃 Ab so jao, kal exam nahi to bhi 😂",
    "Sweet Dreams 💖 Subah milte hain, bye 👋",
    "Good Night 🌙 Charging pe laga do khud ko 🔋",
]
VC = [
    "VC me aao sab log! 🎙️ Maza aayega 🔥",
    "Voice chat chalu hai 🎧 Jaldi join karo!",
    "Sab VC me aa jao yaar, akela bore ho raha hu 😭🎙️",
    "Mic ready karo 🎤 VC me party chal rahi hai 🥳",
]
FUNNY = [
    "Oye! Kidhar ho? Group me aao 😂",
    "Tumhe dhundh dhundh ke thak gaya hu 🥲",
    "Bhai/Behen, zinda ho? Reply to karo 😆",
    "Ek message ka sawaab hai, chhupo mat 😎",
    "Aaj tumhari baari hai, bach ke kahan jaoge 😜",
    "Phone ka network theek hai? Group me aa jao 🤣",
    "Tumhare bina group adhura hai 🥺💖",
    "Hello hello? Mic check 1 2 3 🎤😂",
    "Online ho ya sirf last seen chhupa rakha hai? 🕵️",
    "Chai pee ke aa jao, hum wait kar rahe hain ☕😄",
]
POOL = {"gmtag": GM, "gntag": GN, "vctag": VC, "tagall": FUNNY}


def kb(paused: bool) -> InlineKeyboardMarkup:
    first = (
        InlineKeyboardButton("▶️ Resume", callback_data="tg:resume")
        if paused else InlineKeyboardButton("⏸ Pause", callback_data="tg:pause")
    )
    return InlineKeyboardMarkup([[first, InlineKeyboardButton("⛔ Stop", callback_data="tg:stop")]])


def progress(done: int, total: int, state: str) -> str:
    n = int(10 * done / total) if total else 0
    bar = "▰" * n + "▱" * (10 - n)
    return f"💠 <b>{S('tagging')}</b> • {state}\n<code>{bar}</code>  <b>{done}/{total}</b>"


def build(cfg: dict, mode: str, text_fn, batch: list) -> str:
    style, theme, font = cfg["style"], cfg["theme"], cfg["font"]
    ments = [mention(u, style) for u in batch]
    if style == "emoji":
        mline = " ".join(ments)
    else:
        b = BULLET.get(theme, "•")
        mline = "\n".join(f"{b} {m}" for m in ments)
    text = text_fn()
    body = (f_html(text, font) + "\n\n" if text else "") + mline
    return wrap(theme, f(TITLES[mode], font), body)


async def send_split(client, chat_id, batch, cfg, mode, text_fn):
    msg = build(cfg, mode, text_fn, batch)
    if len(msg) > 3900 and len(batch) > 1:
        h = len(batch) // 2
        await send_split(client, chat_id, batch[:h], cfg, mode, text_fn)
        await send_split(client, chat_id, batch[h:], cfg, mode, text_fn)
        return
    while True:
        try:
            await client.send_message(chat_id, msg, parse_mode=HTML, disable_web_page_preview=True)
            return
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)


async def run_tag(client, message, members, cfg, mode, text_fn):
    chat_id = message.chat.id
    uid = message.from_user.id if message.from_user else 0
    total = len(members)
    if not total:
        await message.reply_text(
            "⚠️ Koi member nahi mila. Mujhe <b>admin</b> banao taaki main members dekh sakun.",
            parse_mode=HTML,
        )
        return
    separate = mode == "tagall"
    per = 1 if separate else int(cfg["per"])
    st = {"stop": False, "paused": False, "go": asyncio.Event(), "by": uid}
    st["go"].set()
    RUN[chat_id] = st

    ctl = await message.reply_text(progress(0, total, "▶️ running"), reply_markup=kb(False), parse_mode=HTML)
    done, err = 0, None
    try:
        for i in range(0, total, per):
            await st["go"].wait()
            if st["stop"]:
                break
            batch = members[i:i + per]
            await send_split(client, chat_id, batch, cfg, mode, text_fn)
            done += len(batch)
            state = "⏸ paused" if st["paused"] else "▶️ running"
            try:
                await ctl.edit_text(progress(done, total, state), reply_markup=kb(st["paused"]), parse_mode=HTML)
            except Exception:
                pass
            await asyncio.sleep(3 if separate else 2.5)
    except Exception as e:  # noqa
        err = str(e)
        log.warning("tagging error: %s", e)
    finally:
        RUN.pop(chat_id, None)

    if err:
        end = f"⚠️ <b>{S('error')}</b>: <code>{err[:100]}</code>"
    elif st["stop"]:
        end = f"⛔ <b>{S('stopped')}</b> • {done}/{total}"
    else:
        end = f"✅ <b>{S('completed')}</b> • {done}/{total}"
    try:
        await ctl.edit_text(end, parse_mode=HTML)
    except Exception:
        pass


async def start_tag(client, message, mode: str, silent: bool = False):
    chat_id = message.chat.id
    if await banned(message):
        return
    cfg = await db.get_chat(chat_id)
    level = cfg["who_tagall"] if mode == "tagall" else cfg["who_all"]
    if not await can_use(client, message, level):
        if not silent:
            names = {"staff": "admins", "owner": "group owner", "botowner": "bot owner"}
            await message.reply_text(f"⛔ Ye command sirf <b>{names.get(level, 'allowed users')}</b> use kar sakte hain.", parse_mode=HTML)
        return
    if chat_id in RUN:
        if not silent:
            await message.reply_text("⏳ Tagging pehle se chal rahi hai. Rokne ke liye /stop.")
        return
    await db.add_group(chat_id, message.chat.title or "")

    custom = extract_text(message)
    members = await fetch_members(client, chat_id, admins_only=(mode == "admins"))
    unreg = await db.unreg_set(chat_id)
    members = [u for u in members if u.id not in unreg]
    if mode == "vctag":
        members.sort(key=status_rank)  # online first
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
    await run_tag(client, message, members, cfg, mode, text_fn)


# ---------------- handlers ----------------
@Client.on_message(filters.group & filters.command("all"))
async def c_all(c, m):
    await start_tag(c, m, "all")


@Client.on_message(filters.group & filters.command("admins"))
async def c_admins(c, m):
    await start_tag(c, m, "admins")


@Client.on_message(filters.group & filters.command("anybody"))
async def c_anybody(c, m):
    await start_tag(c, m, "anybody")


@Client.on_message(filters.group & filters.command("gmtag"))
async def c_gm(c, m):
    await start_tag(c, m, "gmtag")


@Client.on_message(filters.group & filters.command("gntag"))
async def c_gn(c, m):
    await start_tag(c, m, "gntag")


@Client.on_message(filters.group & filters.command("vctag"))
async def c_vc(c, m):
    await start_tag(c, m, "vctag")


@Client.on_message(filters.group & filters.command("tagall"))
async def c_tagall(c, m):
    await start_tag(c, m, "tagall")


@Client.on_message(filters.group & filters.regex(r"(?i)^(@all|all)(\s|$)"))
async def p_all(c, m):
    await start_tag(c, m, "all", silent=True)


@Client.on_message(filters.group & filters.regex(r"(?i)^@admins?(\s|$)"))
async def p_admin(c, m):
    await start_tag(c, m, "admins", silent=True)


@Client.on_message(filters.group & filters.command("stop"))
async def c_stop(c, m):
    st = RUN.get(m.chat.id)
    if not st:
        return await m.reply_text("ℹ️ Abhi koi tagging nahi chal rahi.")
    uid = m.from_user.id if m.from_user else 0
    if uid != st["by"] and not await can_use(c, m, "staff"):
        return await m.reply_text("⛔ Sirf admins ya tagging shuru karne wala rok sakta hai.")
    st["stop"] = True
    st["go"].set()
    await m.reply_text("⛔ Tagging rok di gayi.")


@Client.on_callback_query(filters.regex(r"^tg:(pause|resume|stop)$"))
async def tg_cb(c, q):
    chat_id = q.message.chat.id
    st = RUN.get(chat_id)
    if not st:
        return await q.answer("Tagging chal nahi rahi.", show_alert=True)
    if q.from_user.id != st["by"] and not await is_admin(c, chat_id, q.from_user.id):
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
        await q.answer("⛔ Stopped")
        return
    try:
        await q.message.edit_reply_markup(kb(st["paused"]))
    except Exception:
        pass

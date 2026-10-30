"""/start, /help, /unreg, /reg"""
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb

import database as db
from fonts import S, wrap
from utils import banned, get_me

HTML = ParseMode.HTML


def start_text() -> str:
    body = (
        f"✨ <b>{S('premium tagging bot for telegram')}</b>\n\n"
        f"💠 {S('tag everyone in style')}\n"
        f"💠 {S('fonts, themes and emoji styles')}\n"
        f"💠 {S('welcome with group dp')}\n"
        f"💠 {S('pause, resume and stop buttons')}\n\n"
        f"🛡 {S('add me to your group and make me admin')}"
    )
    return wrap("neon", S("kuku"), body)


HELP = wrap(
    "neon",
    S("commands"),
    "🏷 <b>Tagging</b> <i>(admins)</i>\n"
    "• /all [text] • all • @all\n"
    "• /admins [text] • @admin\n"
    "• /anybody [text]\n"
    "• /gmtag • /gntag • /vctag\n"
    "• /tagall [text] — sabko alag funny msg\n"
    "• /stop — tagging band\n\n"
    "⚙️ <b>Group</b>\n"
    "• /settings — style, per msg, limit, font, theme, access\n"
    "• /unreg — tag list se hato\n"
    "• /reg — wapas aao\n\n"
    "👑 <b>Owner</b>\n"
    "• /broadcast • /stats • /ban • /unban\n\n"
    "💡 Premium emoji text me likhoge to wahi sabhi tak jayega.",
)


async def home_kb():
    me = await get_me_cached()
    return Kb([
        [Btn("➕ Add Me To Group", url=f"https://t.me/{me}?startgroup=true&admin=invite_users+delete_messages")],
        [Btn("📖 Commands", callback_data="hp:help")],
    ])


_uname = None


async def get_me_cached():
    return _uname


@Client.on_message(filters.command("start"))
async def start_cmd(c, m):
    global _uname
    if _uname is None:
        _uname = (await get_me(c)).username
    if await banned(m):
        return
    if m.chat.type == ChatType.PRIVATE and m.from_user:
        await db.add_user(m.from_user.id)
    elif m.chat.type != ChatType.PRIVATE:
        await db.add_group(m.chat.id, m.chat.title or "")
    await m.reply_text(start_text(), reply_markup=await home_kb(), parse_mode=HTML)


@Client.on_message(filters.command("help"))
async def help_cmd(c, m):
    await m.reply_text(HELP, parse_mode=HTML)


@Client.on_callback_query(filters.regex(r"^hp:"))
async def help_cb(c, q):
    global _uname
    if _uname is None:
        _uname = (await get_me(c)).username
    try:
        if q.data == "hp:help":
            await q.message.edit_text(HELP, reply_markup=Kb([[Btn("⬅️ Back", callback_data="hp:back")]]), parse_mode=HTML)
        else:
            await q.message.edit_text(start_text(), reply_markup=await home_kb(), parse_mode=HTML)
    except MessageNotModified:
        pass
    await q.answer()


@Client.on_message(filters.group & filters.command("unreg"))
async def unreg_cmd(c, m):
    if m.from_user:
        await db.unreg_add(m.chat.id, m.from_user.id)
        await m.reply_text("✅ Ab aap tag list se bahar ho. Wapas aane ke liye /reg")


@Client.on_message(filters.group & filters.command("reg"))
async def reg_cmd(c, m):
    if m.from_user:
        await db.unreg_remove(m.chat.id, m.from_user.id)
        await m.reply_text("✅ Aap wapas tag list me aa gaye.")

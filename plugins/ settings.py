"""/settings - button menu (style, per message, limit, font, theme, access, welcome/left)."""
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb

import database as db
from fonts import FONT_NAMES, S, THEME_NAMES, wrap
from utils import can_use, is_admin

HTML = ParseMode.HTML
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


def label(key: str, val) -> str:
    for v, lab in SCHEMA[key][1]:
        if v == str(val):
            return lab
    return str(val)


def main_text(cfg: dict) -> str:
    rows = [
        f"🎨 {S('style')}  ›  <b>{label('style', cfg['style'])}</b>",
        f"📦 {S('per message')}  ›  <b>{cfg['per']}</b>",
        f"🎯 {S('limit')}  ›  <b>{label('limit', cfg['limit'])}</b>",
        f"🔠 {S('font')}  ›  <b>{label('font', cfg['font'])}</b>",
        f"🌈 {S('theme')}  ›  <b>{label('theme', cfg['theme'])}</b>",
        f"👑 /all  ›  <b>{label('who_all', cfg['who_all'])}</b>",
        f"😂 /tagall  ›  <b>{label('who_tagall', cfg['who_tagall'])}</b>",
        f"👋 {S('welcome')}  ›  <b>{'ON' if cfg['welcome'] else 'OFF'}</b>   🚪 {S('left')}  ›  <b>{'ON' if cfg['left'] else 'OFF'}</b>",
    ]
    return wrap("neon", S("kuku settings"), "\n".join(rows))


def kb_main(cfg: dict) -> Kb:
    dot = lambda v: "🟢" if v else "🔴"  # noqa: E731
    return Kb([
        [Btn("🎨 Style", callback_data="st:menu:style"), Btn("📦 Per Msg", callback_data="st:menu:per")],
        [Btn("🎯 Limit", callback_data="st:menu:limit"), Btn("🔠 Font", callback_data="st:menu:font")],
        [Btn("🌈 Theme", callback_data="st:menu:theme"), Btn("👑 /all Access", callback_data="st:menu:who_all")],
        [Btn("😂 /tagall Access", callback_data="st:menu:who_tagall")],
        [Btn(f"{dot(cfg['welcome'])} Welcome", callback_data="st:tog:welcome"),
         Btn(f"{dot(cfg['left'])} Left", callback_data="st:tog:left")],
        [Btn("✖️ Close", callback_data="st:close")],
    ])


def kb_menu(cfg: dict, key: str) -> Kb:
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


@Client.on_message(filters.command("settings"))
async def settings_cmd(c, m):
    if m.chat.type == ChatType.PRIVATE:
        return await m.reply_text("⚙️ Settings group me kholo (mujhe admin banake <code>/settings</code> likho).", parse_mode=HTML)
    if not await can_use(c, m, "staff"):
        return await m.reply_text("⛔ Settings sirf admins badal sakte hain.")
    await db.add_group(m.chat.id, m.chat.title or "")
    cfg = await db.get_chat(m.chat.id)
    await m.reply_text(main_text(cfg), reply_markup=kb_main(cfg), parse_mode=HTML)


@Client.on_callback_query(filters.regex(r"^st:"))
async def settings_cb(c, q):
    chat_id = q.message.chat.id
    if not await is_admin(c, chat_id, q.from_user.id):
        return await q.answer("🛡 Sirf admins settings badal sakte hain.", show_alert=True)
    parts = q.data.split(":")
    act = parts[1]
    cfg = await db.get_chat(chat_id)

    if act == "close":
        await q.message.delete()
        return
    if act == "main":
        await show(q, main_text(cfg), kb_main(cfg))
    elif act == "menu":
        key = parts[2]
        text = wrap("neon", S(SCHEMA[key][0].split(" ", 1)[1]), f"{SCHEMA[key][0]}\n\n👇 {S('select an option')}")
        await show(q, text, kb_menu(cfg, key))
    elif act == "set":
        key, val = parts[2], parts[3]
        await db.set_chat(chat_id, key, int(val) if key in ("per", "limit") else val)
        cfg = await db.get_chat(chat_id)
        text = wrap("neon", S(SCHEMA[key][0].split(" ", 1)[1]), f"✅ {S('saved')}: <b>{label(key, val)}</b>")
        await show(q, text, kb_menu(cfg, key))
        return await q.answer("✅ Saved")
    elif act == "tog":
        key = parts[2]
        await db.set_chat(chat_id, key, not cfg[key])
        cfg = await db.get_chat(chat_id)
        await show(q, main_text(cfg), kb_main(cfg))
    await q.answer()

"""Fonts + neon/premium themes."""
import re

FONT_NAMES = {
    "normal": "Normal",
    "bold": "𝗕𝗼𝗹𝗱",
    "italic": "𝙄𝙩𝙖𝙡𝙞𝙘",
    "script": "𝓢𝓬𝓻𝓲𝓹𝓽",
    "small": "ꜱᴍᴀʟʟ ᴄᴀᴘꜱ",
    "double": "𝔻𝕠𝕦𝕓𝕝𝕖",
}

THEME_NAMES = {
    "neon": "💠 Neon",
    "premium": "👑 Premium",
    "dark": "🌑 Dark Box",
    "minimal": "▫️ Minimal",
    "default": "✨ Default",
}

BULLET = {"neon": "💠", "premium": "✦", "dark": "▸", "minimal": "•", "default": "•"}


def _mk(up: int, lo: int, exc: dict | None = None) -> dict:
    m = {}
    for i in range(26):
        m[chr(65 + i)] = chr(up + i)
        m[chr(97 + i)] = chr(lo + i)
    if exc:
        m.update(exc)
    return m


_SMALL = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ"
_SMALL_MAP = {}
for _i, _ch in enumerate(_SMALL):
    _SMALL_MAP[chr(97 + _i)] = _ch
    _SMALL_MAP[chr(65 + _i)] = _ch

MAPS = {
    "bold": _mk(0x1D5D4, 0x1D5EE),
    "italic": _mk(0x1D63C, 0x1D656),
    "script": _mk(0x1D4D0, 0x1D4EA),
    "double": _mk(0x1D538, 0x1D552, {"C": "ℂ", "H": "ℍ", "N": "ℕ", "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ"}),
    "small": _SMALL_MAP,
}
_TABLES = {k: str.maketrans(v) for k, v in MAPS.items()}
_TOKEN = re.compile(r"(<[^>]*>|&#?\w+;)")


def f(text: str, font: str) -> str:
    """Apply font to plain text."""
    t = _TABLES.get(font)
    return text.translate(t) if t else text


def f_html(html_text: str, font: str) -> str:
    """Apply font to HTML text without touching tags/entities (keeps premium emoji intact)."""
    t = _TABLES.get(font)
    if not t:
        return html_text
    parts = _TOKEN.split(html_text)
    return "".join(p if i % 2 else p.translate(t) for i, p in enumerate(parts))


def S(text: str) -> str:
    """Small caps (used for UI labels)."""
    return text.translate(_TABLES["small"])


def wrap(theme: str, title: str, body: str) -> str:
    """Wrap a body in the chosen theme. `title` must be plain/HTML-safe text."""
    if theme == "neon":
        bar = "▰▱" * 7
        return (
            f"<b>⚡ ⟦ {title} ⟧ ⚡</b>\n<b>{bar}</b>\n\n{body}\n\n<b>{bar}</b>\n"
            f"💠 <i>{S('kuku tag bot')}</i> 💠"
        )
    if theme == "premium":
        return (
            f"✦ ━━━━ ✦ <b>{title}</b> ✦ ━━━━ ✦\n\n{body}\n\n"
            f"✦ ━━━━━━━━━━━━━━ ✦"
        )
    if theme == "dark":
        return f"<blockquote><b>{title}</b>\n\n{body}</blockquote>"
    if theme == "minimal":
        return f"<b>{title}</b>\n{body}"
    return f"✨ <b>{title}</b> ✨\n\n{body}"

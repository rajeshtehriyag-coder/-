"""MongoDB layer (motor). Members are NOT stored - only settings, users, groups, bans, unreg."""
from motor.motor_asyncio import AsyncIOMotorClient

from config import DB_NAME, MONGO_URL

_client = AsyncIOMotorClient(MONGO_URL)
db = _client[DB_NAME]

DEFAULTS = dict(
    style="mention",   # emoji | username | mention | plain
    per=5,             # members per message
    limit=0,           # 0 = all
    font="bold",       # normal | bold | italic | script | small | double
    theme="neon",      # neon | premium | dark | minimal | default
    who_all="staff",   # all | staff | owner | botowner
    who_tagall="staff",
    welcome=True,
    left=True,
)

_cache: dict = {}
_groups: set = set()
_users: set = set()
_bans = None


async def get_chat(chat_id: int) -> dict:
    if chat_id in _cache:
        return _cache[chat_id]
    doc = await db.groups.find_one({"_id": chat_id}) or {}
    cfg = {**DEFAULTS, **{k: v for k, v in doc.items() if k in DEFAULTS}}
    _cache[chat_id] = cfg
    return cfg


async def set_chat(chat_id: int, key: str, value) -> None:
    cfg = await get_chat(chat_id)
    cfg[key] = value
    await db.groups.update_one({"_id": chat_id}, {"$set": {key: value}}, upsert=True)


async def add_group(chat_id: int, title: str) -> None:
    if chat_id in _groups:
        return
    _groups.add(chat_id)
    await db.groups.update_one({"_id": chat_id}, {"$set": {"title": title}}, upsert=True)


async def add_user(user_id: int) -> None:
    if user_id in _users:
        return
    _users.add(user_id)
    await db.users.update_one({"_id": user_id}, {"$set": {"ok": True}}, upsert=True)


# ---- unreg (members who opted out of tagging) ----
async def unreg_set(chat_id: int) -> set:
    doc = await db.unreg.find_one({"_id": chat_id})
    return set(doc.get("users", [])) if doc else set()


async def unreg_add(chat_id: int, user_id: int) -> None:
    await db.unreg.update_one({"_id": chat_id}, {"$addToSet": {"users": user_id}}, upsert=True)


async def unreg_remove(chat_id: int, user_id: int) -> None:
    await db.unreg.update_one({"_id": chat_id}, {"$pull": {"users": user_id}}, upsert=True)


# ---- bans ----
async def _load_bans() -> None:
    global _bans
    if _bans is None:
        _bans = {d["_id"] async for d in db.bans.find()}


async def is_banned(any_id: int) -> bool:
    await _load_bans()
    return any_id in _bans


async def ban(any_id: int) -> None:
    await _load_bans()
    _bans.add(any_id)
    await db.bans.update_one({"_id": any_id}, {"$set": {"ok": True}}, upsert=True)


async def unban(any_id: int) -> None:
    await _load_bans()
    _bans.discard(any_id)
    await db.bans.delete_one({"_id": any_id})


# ---- stats / broadcast ----
async def stats() -> dict:
    await _load_bans()
    return dict(
        users=await db.users.count_documents({}),
        groups=await db.groups.count_documents({}),
        bans=len(_bans),
    )


async def all_targets() -> list:
    ids = [d["_id"] async for d in db.users.find()]
    ids += [d["_id"] async for d in db.groups.find()]
    return ids

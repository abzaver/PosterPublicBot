import aiosqlite
import logging

logger = logging.getLogger(__name__)

DATABASE_NAME = "posterbot.db"

_DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS schema_migrations (
        version     INTEGER PRIMARY KEY,
        applied_at  INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    """CREATE TABLE IF NOT EXISTS workspaces (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_user_id   INTEGER NOT NULL,
        ak_chat_id      INTEGER,
        ok_chat_id      INTEGER,
        status          TEXT    NOT NULL DEFAULT 'pending',
        created_at      INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    """CREATE TABLE IF NOT EXISTS workspace_config (
        workspace_id    INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        key             TEXT    NOT NULL,
        value           TEXT    NOT NULL,
        PRIMARY KEY (workspace_id, key)
    )""",
    """CREATE TABLE IF NOT EXISTS images (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id    INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        chat_id         INTEGER NOT NULL,
        phash           TEXT    NOT NULL,
        msg_id          INTEGER NOT NULL,
        timestamp       INTEGER NOT NULL DEFAULT (unixepoch()),
        file_name       TEXT    NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS posts (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id     INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        bot_msg_id       INTEGER NOT NULL,
        chat_id          INTEGER NOT NULL,
        sender_user_id   INTEGER,
        media_type       TEXT    NOT NULL,
        caption          TEXT    NOT NULL DEFAULT '',
        sender_name      TEXT    NOT NULL DEFAULT '',
        status           TEXT    NOT NULL DEFAULT 'pending',
        published_msg_id INTEGER,
        published_at     INTEGER,
        created_at       INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    """CREATE TABLE IF NOT EXISTS votes (
        workspace_id    INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        post_id         INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
        user_id         INTEGER NOT NULL,
        reaction        TEXT    NOT NULL,
        updated_at      INTEGER NOT NULL DEFAULT (unixepoch()),
        PRIMARY KEY (post_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS texts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id    INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        chat_id         INTEGER NOT NULL,
        msg_id          INTEGER NOT NULL,
        normalized_hash TEXT    NOT NULL,
        timestamp       INTEGER NOT NULL DEFAULT (unixepoch())
    )""",
    "CREATE INDEX IF NOT EXISTS idx_images_workspace  ON images(workspace_id)",
    "CREATE INDEX IF NOT EXISTS idx_images_phash      ON images(phash)",
    "CREATE INDEX IF NOT EXISTS idx_posts_workspace   ON posts(workspace_id)",
    "CREATE INDEX IF NOT EXISTS idx_votes_post        ON votes(post_id)",
    "CREATE INDEX IF NOT EXISTS idx_texts_workspace   ON texts(workspace_id)",
    "CREATE INDEX IF NOT EXISTS idx_workspaces_owner  ON workspaces(owner_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_workspaces_ak     ON workspaces(ak_chat_id)",
    "CREATE INDEX IF NOT EXISTS idx_workspaces_ok     ON workspaces(ok_chat_id)",
]

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DATABASE_NAME)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
        for stmt in _DDL_STATEMENTS:
            await _db.execute(stmt)
        await _db.commit()
        logger.info("Database opened: %s", DATABASE_NAME)
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
        logger.info("Database closed")


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

async def create_workspace(owner_user_id: int) -> int:
    db = await get_db()
    async with db.execute(
        "INSERT INTO workspaces (owner_user_id) VALUES (?)", (owner_user_id,)
    ) as cur:
        workspace_id = cur.lastrowid
    await db.commit()
    return workspace_id


async def get_workspace_by_owner(owner_user_id: int) -> list[aiosqlite.Row]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM workspaces WHERE owner_user_id = ? ORDER BY id", (owner_user_id,)
    ) as cur:
        return await cur.fetchall()


async def get_workspace_by_ak(ak_chat_id: int) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM workspaces WHERE ak_chat_id = ? AND status = 'active' LIMIT 1",
        (ak_chat_id,),
    ) as cur:
        return await cur.fetchone()


async def get_workspace_by_ok(ok_chat_id: int) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM workspaces WHERE ok_chat_id = ? AND status = 'active' LIMIT 1",
        (ok_chat_id,),
    ) as cur:
        return await cur.fetchone()


async def set_workspace_ak(workspace_id: int, ak_chat_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE workspaces SET ak_chat_id = ? WHERE id = ?", (ak_chat_id, workspace_id)
    )
    await _try_activate_workspace(db, workspace_id)
    await db.commit()


async def set_workspace_ok(workspace_id: int, ok_chat_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE workspaces SET ok_chat_id = ? WHERE id = ?", (ok_chat_id, workspace_id)
    )
    await _try_activate_workspace(db, workspace_id)
    await db.commit()


async def _try_activate_workspace(db: aiosqlite.Connection, workspace_id: int) -> None:
    async with db.execute(
        "SELECT ak_chat_id, ok_chat_id FROM workspaces WHERE id = ?", (workspace_id,)
    ) as cur:
        row = await cur.fetchone()
    if row and row["ak_chat_id"] and row["ok_chat_id"]:
        await db.execute(
            "UPDATE workspaces SET status = 'active' WHERE id = ?", (workspace_id,)
        )


async def detach_ok(workspace_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE workspaces SET ok_chat_id = NULL, status = 'pending' WHERE id = ?",
        (workspace_id,),
    )
    await db.commit()


async def deactivate_workspace(workspace_id: int) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE workspaces SET status = 'inactive' WHERE id = ?", (workspace_id,)
    )
    await db.commit()


async def delete_workspace(workspace_id: int, owner_user_id: int) -> bool:
    """Удаляет workspace. Возвращает True если удалил, False если не нашёл или не владелец."""
    db = await get_db()
    async with db.execute(
        "SELECT id FROM workspaces WHERE id = ? AND owner_user_id = ?",
        (workspace_id, owner_user_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return False
    await db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Workspace config
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, str] = {
    "hash_threshold":    "10",
    "vote_threshold":    "2",
    "autopublish":       "off",
    "on_bayan_action":   "warn",
    "gotcha":            "off",
    "gotcha_template":   "{user}, чо поменял {old} на {new}? 👀",
    "positive_reactions": "👍 ❤️ ❤ 🔥",
    "negative_reactions": "👎 💩",
    "text_threshold":    "80",
    "text_min_len":      "20",
}


async def get_config(workspace_id: int, key: str) -> str:
    db = await get_db()
    async with db.execute(
        "SELECT value FROM workspace_config WHERE workspace_id = ? AND key = ?",
        (workspace_id, key),
    ) as cur:
        row = await cur.fetchone()
    return row["value"] if row else DEFAULTS.get(key, "")


async def set_config(workspace_id: int, key: str, value: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO workspace_config (workspace_id, key, value) VALUES (?, ?, ?)"
        " ON CONFLICT(workspace_id, key) DO UPDATE SET value = excluded.value",
        (workspace_id, key, value),
    )
    await db.commit()


async def get_all_config(workspace_id: int) -> dict[str, str]:
    db = await get_db()
    async with db.execute(
        "SELECT key, value FROM workspace_config WHERE workspace_id = ?", (workspace_id,)
    ) as cur:
        rows = await cur.fetchall()
    result = dict(DEFAULTS)
    result.update({r["key"]: r["value"] for r in rows})
    return result


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

async def add_image(workspace_id: int, chat_id: int, phash: str, msg_id: int, file_name: str = "") -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO images (workspace_id, chat_id, phash, msg_id, file_name) VALUES (?, ?, ?, ?, ?)",
        (workspace_id, chat_id, phash, msg_id, file_name),
    )
    await db.commit()


async def search_images_by_hash(workspace_id: int, phash: str, threshold: int) -> list[aiosqlite.Row]:
    db = await get_db()
    await db.create_function("hexhammdist", 2, _hamming_distance)
    async with db.execute(
        "SELECT *, hexhammdist(phash, ?) AS hd FROM images"
        " WHERE workspace_id = ? AND hd <= ? ORDER BY hd",
        (phash, workspace_id, threshold),
    ) as cur:
        return await cur.fetchall()


async def get_image_by_msg(workspace_id: int, chat_id: int, msg_id: int) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM images WHERE workspace_id = ? AND chat_id = ? AND msg_id = ? LIMIT 1",
        (workspace_id, chat_id, msg_id),
    ) as cur:
        return await cur.fetchone()


async def delete_image(image_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM images WHERE id = ?", (image_id,))
    await db.commit()


async def image_exists(workspace_id: int, chat_id: int, msg_id: int) -> bool:
    db = await get_db()
    async with db.execute(
        "SELECT 1 FROM images WHERE workspace_id = ? AND chat_id = ? AND msg_id = ? LIMIT 1",
        (workspace_id, chat_id, msg_id),
    ) as cur:
        return await cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------

async def add_post(workspace_id: int, bot_msg_id: int, chat_id: int,
                   sender_user_id: int | None, media_type: str,
                   caption: str = "", sender_name: str = "") -> int:
    db = await get_db()
    async with db.execute(
        "INSERT INTO posts (workspace_id, bot_msg_id, chat_id, sender_user_id, media_type, caption, sender_name)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (workspace_id, bot_msg_id, chat_id, sender_user_id, media_type, caption, sender_name),
    ) as cur:
        post_id = cur.lastrowid
    await db.commit()
    return post_id


async def get_post_by_msg(workspace_id: int, bot_msg_id: int) -> aiosqlite.Row | None:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM posts WHERE workspace_id = ? AND bot_msg_id = ? LIMIT 1",
        (workspace_id, bot_msg_id),
    ) as cur:
        return await cur.fetchone()


async def mark_post_published(post_id: int, published_msg_id: int) -> bool:
    """Атомарно помечает пост опубликованным. Возвращает True если успешно, False если уже опубликован."""
    db = await get_db()
    async with db.execute(
        "UPDATE posts SET status = 'published', published_msg_id = ?, published_at = unixepoch()"
        " WHERE id = ? AND status = 'pending'",
        (published_msg_id, post_id),
    ) as cur:
        updated = cur.rowcount
    await db.commit()
    return updated > 0


# ---------------------------------------------------------------------------
# Votes
# ---------------------------------------------------------------------------

async def upsert_vote(workspace_id: int, post_id: int, user_id: int, reaction: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO votes (workspace_id, post_id, user_id, reaction, updated_at)"
        " VALUES (?, ?, ?, ?, unixepoch())"
        " ON CONFLICT(post_id, user_id) DO UPDATE SET reaction = excluded.reaction, updated_at = excluded.updated_at",
        (workspace_id, post_id, user_id, reaction),
    )
    await db.commit()


async def delete_vote(post_id: int, user_id: int) -> None:
    db = await get_db()
    await db.execute("DELETE FROM votes WHERE post_id = ? AND user_id = ?", (post_id, user_id))
    await db.commit()


async def count_votes(post_id: int, positive_reactions: list[str]) -> tuple[int, int]:
    db = await get_db()
    placeholders = ",".join("?" * len(positive_reactions))
    async with db.execute(
        f"SELECT reaction FROM votes WHERE post_id = ?", (post_id,)
    ) as cur:
        rows = await cur.fetchall()
    positive = sum(1 for r in rows if r["reaction"] in positive_reactions)
    negative = len(rows) - positive
    return positive, negative


# ---------------------------------------------------------------------------
# Texts
# ---------------------------------------------------------------------------

async def add_text(workspace_id: int, chat_id: int, msg_id: int, normalized_hash: str) -> None:
    db = await get_db()
    await db.execute(
        "INSERT INTO texts (workspace_id, chat_id, msg_id, normalized_hash) VALUES (?, ?, ?, ?)",
        (workspace_id, chat_id, msg_id, normalized_hash),
    )
    await db.commit()


async def search_texts_by_hash(workspace_id: int, normalized_hash: str) -> list[aiosqlite.Row]:
    db = await get_db()
    async with db.execute(
        "SELECT * FROM texts WHERE workspace_id = ? AND normalized_hash = ?",
        (workspace_id, normalized_hash),
    ) as cur:
        return await cur.fetchall()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hamming_distance(a: str, b: str) -> int:
    if len(a) != len(b):
        return max(len(a), len(b)) * 4
    return sum(bin(int(x, 16) ^ int(y, 16)).count("1") for x, y in zip(a, b))

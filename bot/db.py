from __future__ import annotations

import os

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    role TEXT DEFAULT 'assistant',
    model TEXT DEFAULT 'chat',
    requests INTEGER DEFAULT 0,
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS emoji(plain TEXT PRIMARY KEY, custom_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


class DB:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection

    async def init(self) -> None:
        if os.path.dirname(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        await self.conn.close()

    # --- пользователи ---
    async def touch_user(self, user_id: int, name: str) -> tuple[str, str]:
        await self.conn.execute(
            "INSERT INTO users(user_id, name) VALUES(?, ?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name",
            (user_id, name),
        )
        await self.conn.commit()
        return await self.user_settings(user_id)

    async def user_settings(self, user_id: int) -> tuple[str, str]:
        cur = await self.conn.execute("SELECT role, model FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return (row[0], row[1]) if row else ("assistant", "chat")

    async def set_role(self, user_id: int, role: str) -> None:
        await self.conn.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
        await self.conn.commit()

    async def set_model(self, user_id: int, model: str) -> None:
        await self.conn.execute("UPDATE users SET model=? WHERE user_id=?", (model, user_id))
        await self.conn.commit()

    async def count_request(self, user_id: int) -> None:
        await self.conn.execute("UPDATE users SET requests=requests+1 WHERE user_id=?", (user_id,))
        await self.conn.commit()

    async def stats(self) -> tuple[int, int, int]:
        users = (await (await self.conn.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        reqs = (await (await self.conn.execute("SELECT COALESCE(SUM(requests),0) FROM users")).fetchone())[0]
        msgs = (await (await self.conn.execute("SELECT COUNT(*) FROM messages")).fetchone())[0]
        return users, reqs, msgs

    # --- история ---
    async def history(self, chat_id: int, limit: int) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit)
        )
        rows = await cur.fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    async def add_messages(self, chat_id: int, *pairs: tuple[str, str]) -> None:
        await self.conn.executemany(
            "INSERT INTO messages(chat_id, role, content) VALUES(?,?,?)", [(chat_id, r, c) for r, c in pairs]
        )
        await self.conn.commit()

    async def pop_last_exchange(self, chat_id: int) -> str | None:
        """Удаляет последний ответ ассистента и возвращает последний вопрос юзера (тоже удаляя его)."""
        cur = await self.conn.execute(
            "SELECT id, role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 2", (chat_id,)
        )
        rows = await cur.fetchall()
        if len(rows) < 2 or rows[0][1] != "assistant" or rows[1][1] != "user":
            return None
        await self.conn.execute("DELETE FROM messages WHERE id IN (?, ?)", (rows[0][0], rows[1][0]))
        await self.conn.commit()
        return rows[1][2]

    async def clear(self, chat_id: int) -> None:
        await self.conn.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
        await self.conn.commit()

    # --- эмодзи / meta ---
    async def load_emoji(self) -> dict[str, str]:
        cur = await self.conn.execute("SELECT plain, custom_id FROM emoji")
        return {p: c for p, c in await cur.fetchall()}

    async def save_emoji(self, mapping: dict[str, str]) -> None:
        await self.conn.executemany(
            "INSERT INTO emoji(plain, custom_id) VALUES(?,?) ON CONFLICT(plain) DO UPDATE SET custom_id=excluded.custom_id",
            list(mapping.items()),
        )
        await self.conn.commit()

    async def clear_emoji(self) -> None:
        await self.conn.execute("DELETE FROM emoji")
        await self.conn.commit()

    async def get_meta(self, key: str) -> str | None:
        row = await (await self.conn.execute("SELECT value FROM meta WHERE key=?", (key,))).fetchone()
        return row[0] if row else None

    async def set_meta(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value)
        )
        await self.conn.commit()

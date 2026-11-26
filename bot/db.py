"""Хранилище на Supabase (PostgREST через httpx — без драйверов и пулов соединений, удобно для serverless)."""
from __future__ import annotations

import random

import httpx


class DB:
    def __init__(self, url: str, key: str):
        self.http = httpx.AsyncClient(
            base_url=url.rstrip("/") + "/rest/v1",
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=15,
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def _req(self, method: str, path: str, *, prefer: str | None = None, **kw) -> httpx.Response:
        headers = {"Prefer": prefer} if prefer else None
        r = await self.http.request(method, path, headers=headers, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase {method} {path}: {r.status_code} {r.text[:300]}")
        return r

    async def _upsert(self, table: str, rows: list[dict], conflict: str) -> None:
        await self._req(
            "POST", f"/{table}", params={"on_conflict": conflict}, json=rows,
            prefer="resolution=merge-duplicates,return=minimal",
        )

    # --- дедупликация webhook-ов ---
    async def claim_update(self, update_id: int) -> bool:
        r = await self._req(
            "POST", "/processed_updates", params={"on_conflict": "update_id"}, json=[{"update_id": update_id}],
            prefer="resolution=ignore-duplicates,return=representation",
        )
        if random.random() < 0.02:  # изредка чистим старое
            await self._req("DELETE", "/processed_updates", params={"created_at": "lt." + _ago()})
        return bool(r.json())

    # --- пользователи ---
    async def touch_user(self, user_id: int, name: str) -> tuple[str, str]:
        await self._upsert("users", [{"user_id": user_id, "name": name}], "user_id")
        return await self.user_settings(user_id)

    async def user_settings(self, user_id: int) -> tuple[str, str]:
        r = await self._req("GET", "/users", params={"user_id": f"eq.{user_id}", "select": "role,model"})
        rows = r.json()
        return (rows[0]["role"], rows[0]["model"]) if rows else ("assistant", "chat")

    async def _patch_user(self, user_id: int, data: dict) -> None:
        await self._req("PATCH", "/users", params={"user_id": f"eq.{user_id}"}, json=data, prefer="return=minimal")

    async def set_role(self, user_id: int, role: str) -> None:
        await self._patch_user(user_id, {"role": role})

    async def set_model(self, user_id: int, model: str) -> None:
        await self._patch_user(user_id, {"model": model})

    async def count_request(self, user_id: int) -> None:
        await self._req("POST", "/rpc/increment_requests", json={"p_user_id": user_id})

    async def stats(self) -> tuple[int, int, int]:
        d = (await self._req("POST", "/rpc/bot_stats", json={})).json()
        return d["users"], d["requests"], d["messages"]

    # --- история ---
    async def history(self, chat_id: int, limit: int) -> list[dict]:
        r = await self._req(
            "GET", "/messages",
            params={"chat_id": f"eq.{chat_id}", "select": "role,content", "order": "id.desc", "limit": limit},
        )
        return list(reversed(r.json()))

    async def add_messages(self, chat_id: int, *pairs: tuple[str, str]) -> None:
        await self._req(
            "POST", "/messages", json=[{"chat_id": chat_id, "role": r, "content": c} for r, c in pairs],
            prefer="return=minimal",
        )

    async def pop_last_exchange(self, chat_id: int) -> str | None:
        r = await self._req(
            "GET", "/messages",
            params={"chat_id": f"eq.{chat_id}", "select": "id,role,content", "order": "id.desc", "limit": 2},
        )
        rows = r.json()
        if len(rows) < 2 or rows[0]["role"] != "assistant" or rows[1]["role"] != "user":
            return None
        ids = ",".join(str(x["id"]) for x in rows)
        await self._req("DELETE", "/messages", params={"id": f"in.({ids})"})
        return rows[1]["content"]

    async def clear(self, chat_id: int) -> None:
        await self._req("DELETE", "/messages", params={"chat_id": f"eq.{chat_id}"})

    # --- эмодзи / meta ---
    async def load_emoji(self) -> dict[str, str]:
        r = await self._req("GET", "/emoji", params={"select": "plain,custom_id", "limit": 5000})
        return {x["plain"]: x["custom_id"] for x in r.json()}

    async def save_emoji(self, mapping: dict[str, str]) -> None:
        await self._upsert("emoji", [{"plain": p, "custom_id": c} for p, c in mapping.items()], "plain")

    async def clear_emoji(self) -> None:
        await self._req("DELETE", "/emoji", params={"plain": "not.is.null"})

    async def get_meta(self, key: str) -> str | None:
        r = await self._req("GET", "/meta", params={"key": f"eq.{key}", "select": "value"})
        rows = r.json()
        return rows[0]["value"] if rows else None

    async def set_meta(self, key: str, value: str) -> None:
        await self._upsert("meta", [{"key": key, "value": value}], "key")


def _ago() -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

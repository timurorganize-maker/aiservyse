"""Vercel entrypoint: Telegram webhook + одноразовая настройка вебхука."""
from __future__ import annotations

import hmac
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram.types import Update  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402

from bot.app import COMMANDS, get_context  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("webhook")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/")
@app.get("/api")
@app.get("/api/index")
async def health():
    return {"ok": True, "service": "deepseek-telegram-bot"}


@app.post("/api/webhook")
@app.post("/webhook")
@app.post("/api/index")
async def webhook(request: Request):
    ctx = await get_context()
    secret = ctx.cfg.webhook_secret
    if not secret or not hmac.compare_digest(request.headers.get("x-telegram-bot-api-secret-token", ""), secret):
        raise HTTPException(403, "forbidden")
    update = Update.model_validate(await request.json(), context={"bot": ctx.bot})
    try:
        # Telegram повторяет доставку при таймауте — отсекаем дубли
        if not await ctx.db.claim_update(update.update_id):
            return {"ok": True, "duplicate": True}
        # Выполняем ДО ответа: после ответа serverless-функция замораживается
        await ctx.dp.feed_update(ctx.bot, update)
    except Exception:  # noqa: BLE001
        log.exception("update failed")  # всегда 200, иначе Telegram будет слать повторно
    return {"ok": True}


@app.get("/api/setup")
@app.get("/setup")
async def setup(request: Request, secret: str = ""):
    """Открой один раз после деплоя: /api/setup?secret=<WEBHOOK_SECRET> — ставит вебхук и команды."""
    ctx = await get_context()
    if not ctx.cfg.webhook_secret or not hmac.compare_digest(secret, ctx.cfg.webhook_secret):
        raise HTTPException(403, "forbidden")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    url = f"https://{host}/api/webhook"
    await ctx.bot.set_webhook(
        url,
        secret_token=ctx.cfg.webhook_secret,
        allowed_updates=ctx.dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )
    await ctx.bot.set_my_commands(COMMANDS)
    me = await ctx.bot.get_me()
    return {"ok": True, "bot": f"@{me.username}", "webhook": url}

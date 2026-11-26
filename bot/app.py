"""Общая сборка приложения: используется и webhook-ом (Vercel), и локальным polling-ом."""
from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from . import handlers
from .config import Config, load_config
from .db import DB
from .deepseek import DeepSeek
from .emoji import PremiumEmoji

COMMANDS = [
    BotCommand(command="new", description="🧹 Новый диалог"),
    BotCommand(command="role", description="🎭 Выбрать роль"),
    BotCommand(command="model", description="🧠 Выбрать модель"),
    BotCommand(command="help", description="❓ Справка"),
]


@dataclass
class Context:
    cfg: Config
    bot: Bot
    dp: Dispatcher
    db: DB


_ctx: Context | None = None


async def get_context() -> Context:
    global _ctx
    if _ctx:
        return _ctx
    cfg = load_config()
    db = DB(cfg.supabase_url, cfg.supabase_key)
    emoji = PremiumEmoji()
    handlers.cfg, handlers.db, handlers.ai, handlers.emoji = cfg, db, DeepSeek(cfg), emoji
    await handlers.refresh_shared_state()
    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    dp = Dispatcher()
    dp.include_router(handlers.router)
    _ctx = Context(cfg, bot, dp, db)
    return _ctx

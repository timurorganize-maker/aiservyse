from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from . import handlers
from .config import load_config
from .db import DB
from .deepseek import DeepSeek
from .emoji import PremiumEmoji


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()

    db = DB(cfg.db_path)
    await db.init()
    emoji = PremiumEmoji()
    emoji.update(await db.load_emoji())
    handlers.cfg, handlers.db, handlers.ai, handlers.emoji = cfg, db, DeepSeek(cfg), emoji
    # режим эмодзи: берём последний известный статус премиума админа (обновится при его сообщении)
    handlers._sync_emoji_mode((await db.get_meta("admin_premium")) == "1")

    bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    await bot.set_my_commands(
        [
            BotCommand(command="new", description="🧹 Новый диалог"),
            BotCommand(command="role", description="🎭 Выбрать роль"),
            BotCommand(command="model", description="🧠 Выбрать модель"),
            BotCommand(command="help", description="❓ Справка"),
        ]
    )
    dp = Dispatcher()
    dp.include_router(handlers.router)
    me = await bot.get_me()
    logging.info("Бот @%s запущен", me.username)
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

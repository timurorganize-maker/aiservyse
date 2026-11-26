"""Локальный запуск через long polling (для разработки). На Vercel работает webhook: api/index.py."""
from __future__ import annotations

import asyncio
import logging

from .app import COMMANDS, get_context


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ctx = await get_context()
    await ctx.bot.delete_webhook()  # polling и webhook несовместимы
    await ctx.bot.set_my_commands(COMMANDS)
    me = await ctx.bot.get_me()
    logging.info("Бот @%s запущен (polling)", me.username)
    try:
        await ctx.dp.start_polling(ctx.bot)
    finally:
        await ctx.db.close()
        await ctx.bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

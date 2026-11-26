"""Живой стриминг ответа в Telegram: одно сообщение редактируется, длинный текст уходит в новые."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from .emoji import PremiumEmoji
from .formatting import md_to_html, split_markdown

log = logging.getLogger(__name__)
CURSOR = " ▍"


class Streamer:
    def __init__(self, bot: Bot, chat_id: int, emoji: PremiumEmoji):
        self.bot, self.chat_id, self.emoji = bot, chat_id, emoji
        self.msgs: list[list] = []  # [message_id, last_rendered]

    def _render(self, md: str, cursor: bool) -> str:
        out = self.emoji.apply(md_to_html(md)) or "…"
        return out + (CURSOR if cursor else "")

    async def _retry(self, fn, *a, **kw):
        for _ in range(3):
            try:
                return await fn(*a, **kw)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 0.5)
        return None

    async def _send(self, html: str, md: str, markup=None) -> int | None:
        try:
            m = await self._retry(self.bot.send_message, self.chat_id, html, reply_markup=markup)
        except TelegramBadRequest as e:
            log.warning("HTML rejected (%s), sending plain", e)
            m = await self._retry(self.bot.send_message, self.chat_id, md[:4096], parse_mode=None, reply_markup=markup)
        return m.message_id if m else None

    async def _edit(self, idx: int, html: str, md: str, markup=None) -> None:
        mid = self.msgs[idx][0]
        try:
            await self._retry(self.bot.edit_message_text, html, chat_id=self.chat_id, message_id=mid, reply_markup=markup)
        except TelegramBadRequest as e:
            if "not modified" in str(e):
                return
            log.warning("HTML edit rejected (%s), plain fallback", e)
            try:
                await self._retry(
                    self.bot.edit_message_text, md[:4096], chat_id=self.chat_id, message_id=mid,
                    parse_mode=None, reply_markup=markup,
                )
            except TelegramBadRequest:
                pass

    async def start(self, placeholder_md: str) -> None:
        html = self._render(placeholder_md, cursor=False)
        mid = await self._send(html, placeholder_md)
        if mid:
            self.msgs.append([mid, html])

    async def update(self, text: str, final: bool = False, markup: InlineKeyboardMarkup | None = None) -> None:
        chunks = split_markdown(text)
        for i, chunk in enumerate(chunks):
            last = i == len(chunks) - 1
            html = self._render(chunk, cursor=last and not final)
            kb = markup if (final and last) else None
            if i < len(self.msgs):
                if html != self.msgs[i][1] or kb:
                    await self._edit(i, html, chunk, kb)
                    self.msgs[i][1] = html
            else:
                mid = await self._send(html, chunk, kb)
                if mid:
                    self.msgs.append([mid, html])

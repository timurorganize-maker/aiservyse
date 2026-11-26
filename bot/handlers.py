from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from collections import defaultdict

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from openai import APIConnectionError, APIStatusError, RateLimitError

from .config import Config
from .db import DB
from .deepseek import ROLES, DeepSeek
from .emoji import PremiumEmoji
from .streamer import Streamer

log = logging.getLogger(__name__)
router = Router()

EDIT_INTERVAL = 1.0  # сек между редактированиями (лимиты Telegram)
MAX_HISTORY_CHARS = 24000

# Заполняется в main.py
cfg: Config
db: DB
ai: DeepSeek
emoji: PremiumEmoji
_last_refresh = 0.0
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def B(s: str) -> str:
    """Пропускает текст интерфейса через тот же пайплайн (markdown -> html -> премиум-эмодзи)."""
    from .formatting import md_to_html

    return emoji.apply(md_to_html(s))


def after_answer_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Заново", callback_data="regen"),
                InlineKeyboardButton(text="🧹 Новый диалог", callback_data="new"),
            ]
        ]
    )


async def refresh_shared_state() -> None:
    """В serverless несколько инстансов: раз в минуту подтягиваем эмодзи и статус админа из БД."""
    global _last_refresh
    if time.monotonic() - _last_refresh < 60:
        return
    _last_refresh = time.monotonic()
    emoji.clear()
    emoji.update(await db.load_emoji())
    _sync_emoji_mode((await db.get_meta("admin_premium")) == "1")


# ---------- доступ ----------
@router.message.outer_middleware()
async def access_mw(handler, event: Message, data):
    user = event.from_user
    if not user or event.chat.type != "private":
        return
    await refresh_shared_state()
    if user.id in cfg.admin_ids and user.is_premium is not None:
        await db.set_meta("admin_premium", "1" if user.is_premium else "0")
        _sync_emoji_mode(user.is_premium)
    if not cfg.is_allowed(user.id):
        await event.answer(B("🔒 У тебя нет доступа к этому боту."))
        return
    await db.touch_user(user.id, user.full_name)
    return await handler(event, data)


@router.callback_query.outer_middleware()
async def access_cb_mw(handler, event: CallbackQuery, data):
    await refresh_shared_state()
    if not cfg.is_allowed(event.from_user.id):
        return await event.answer("Нет доступа", show_alert=True)
    return await handler(event, data)


def _sync_emoji_mode(admin_premium: bool | None) -> None:
    if cfg.premium_emoji == "on":
        emoji.enabled = True
    elif cfg.premium_emoji == "off":
        emoji.enabled = False
    else:
        emoji.enabled = bool(admin_premium) if cfg.admin_ids else True


# ---------- команды ----------
@router.message(Command("start"))
async def cmd_start(m: Message):
    name = html.escape(m.from_user.first_name or "друг")
    await m.answer(
        B(
            f"✨ **Привет, {name}!**\n\n"
            "Я — ИИ-ассистент на базе **DeepSeek**. Просто напиши мне сообщение — "
            "отвечу, помогу с кодом, текстом, учёбой и идеями.\n\n"
            "💬 Помню контекст диалога\n"
            "🎭 /role — сменить роль\n"
            "🧠 /model — быстрый или думающий режим\n"
            "🧹 /new — начать заново\n"
            "❓ /help — все команды"
        )
    )


@router.message(Command("help"))
async def cmd_help(m: Message):
    extra = (
        "\n\n**Для админа:**\n/status — состояние бота\n"
        "/emojipack `ссылка` — подключить набор премиум-эмодзи\n"
        "/emojiid — id эмодзи из сообщения (ответом на него)\n/emojireset — сбросить премиум-эмодзи"
        if cfg.is_admin(m.from_user.id)
        else ""
    )
    await m.answer(
        B(
            "❓ **Команды**\n\n"
            "/new — новый диалог (очистить память)\n"
            "/role — выбрать роль\n"
            "/model — выбрать модель\n"
            "/help — эта справка" + extra
        )
    )


@router.message(Command("new"))
async def cmd_new(m: Message):
    await db.clear(m.chat.id)
    await m.answer(B("🧹 Диалог очищен. Начнём с чистого листа!"))


@router.callback_query(F.data == "new")
async def cb_new(c: CallbackQuery):
    await db.clear(c.message.chat.id)
    await c.answer("Диалог очищен")
    await c.message.answer(B("🧹 Диалог очищен. Начнём с чистого листа!"))


@router.message(Command("role"))
async def cmd_role(m: Message):
    cur, _ = await db.user_settings(m.from_user.id)
    rows = [
        [InlineKeyboardButton(text=("✅ " if k == cur else "") + v[0], callback_data=f"role:{k}")]
        for k, v in ROLES.items()
    ]
    await m.answer(B("🎭 **Выбери роль** — она определяет стиль ответов:"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("role:"))
async def cb_role(c: CallbackQuery):
    key = c.data.split(":", 1)[1]
    if key not in ROLES:
        return await c.answer()
    await db.set_role(c.from_user.id, key)
    await db.clear(c.message.chat.id)
    await c.answer("Роль изменена")
    await c.message.edit_text(B(f"🎭 Роль: **{ROLES[key][0]}**\nДиалог начат заново."))


@router.message(Command("model"))
async def cmd_model(m: Message):
    _, cur = await db.user_settings(m.from_user.id)
    opts = [("chat", "⚡ Быстрая (deepseek-chat)"), ("reasoner", "🧠 Думающая (deepseek-reasoner)")]
    rows = [[InlineKeyboardButton(text=("✅ " if k == cur else "") + t, callback_data=f"model:{k}")] for k, t in opts]
    await m.answer(
        B("🧠 **Выбери режим**\n\n⚡ быстрые ответы\n🧠 рассуждает дольше — лучше для логики, математики и сложного кода"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("model:"))
async def cb_model(c: CallbackQuery):
    kind = c.data.split(":", 1)[1]
    if kind not in ("chat", "reasoner"):
        return await c.answer()
    await db.set_model(c.from_user.id, kind)
    await c.answer("Режим изменён")
    await c.message.edit_text(B(f"🧠 Режим: **{'думающая' if kind == 'reasoner' else 'быстрая'}**"))


# ---------- админ / премиум-эмодзи ----------
def _admin_only(m: Message) -> bool:
    return cfg.is_admin(m.from_user.id)


@router.message(Command("status"), _admin_only)
async def cmd_status(m: Message):
    users, reqs, msgs = await db.stats()
    prem = await db.get_meta("admin_premium")
    await m.answer(
        B(
            "📊 **Статус**\n\n"
            f"👥 Пользователей: **{users}**\n💬 Запросов: **{reqs}**\n🗂 Сообщений в памяти: **{msgs}**\n"
            f"🧩 Модели: `{cfg.model}` / `{cfg.reasoner_model}`\n"
            f"💎 Премиум у админа: **{'да' if prem == '1' else 'нет/неизвестно'}**\n"
            f"✨ Премиум-эмодзи: **{'включены' if emoji.enabled else 'выключены'}** "
            f"(режим `{cfg.premium_emoji}`, привязано {len(emoji.mapping)})"
        )
    )


@router.message(Command("emojiid"), _admin_only)
async def cmd_emojiid(m: Message):
    src = m.reply_to_message or m
    ents = [e for e in (src.entities or []) if e.type == "custom_emoji"]
    if not ents:
        return await m.answer(B("Ответь командой на сообщение с премиум-эмодзи."))
    lines = [f"{(src.text or '')[e.offset:e.offset + e.length]} — `{e.custom_emoji_id}`" for e in ents]
    await m.answer(B("🆔 **ID эмодзи**\n\n" + "\n".join(lines)))


@router.message(Command("emojipack"), _admin_only)
async def cmd_emojipack(m: Message, command: CommandObject, bot: Bot):
    arg = (command.args or "").strip()
    name = re.sub(r"^.*/addemoji/", "", arg).strip("/ ")
    if not name:
        return await m.answer(B("Использование: `/emojipack https://t.me/addemoji/НазваниеНабора`"))
    try:
        pack = await bot.get_sticker_set(name)
    except Exception as e:  # noqa: BLE001
        return await m.answer(B(f"⚠️ Не нашёл набор: `{html.escape(str(e))}`"))
    mapping = {s.emoji: s.custom_emoji_id for s in pack.stickers if s.custom_emoji_id and s.emoji}
    if not mapping:
        return await m.answer(B("⚠️ В наборе нет кастомных эмодзи."))
    emoji.update(mapping)
    await db.save_emoji(mapping)
    sample = " ".join(list(mapping)[:12])
    await m.answer(B(f"✅ Подключено **{len(mapping)}** премиум-эмодзи из «{html.escape(pack.title)}»\n\n{sample}"))


@router.message(Command("emojireset"), _admin_only)
async def cmd_emojireset(m: Message):
    emoji.clear()
    await db.clear_emoji()
    await m.answer(B("🧹 Премиум-эмодзи сброшены."))


# ---------- диалог ----------
def _trim(history: list[dict]) -> list[dict]:
    total, out = 0, []
    for msg in reversed(history):
        total += len(msg["content"])
        if total > MAX_HISTORY_CHARS and out:
            break
        out.append(msg)
    out.reverse()
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


async def respond(bot: Bot, chat_id: int, user_id: int, text: str) -> None:
    lock = _locks[chat_id]
    if lock.locked():
        await bot.send_message(chat_id, B("⏳ Подожди, я ещё отвечаю на предыдущий вопрос."))
        return
    async with lock:
        role, kind = await db.user_settings(user_id)
        history = _trim(await db.history(chat_id, cfg.history_limit))
        history.append({"role": "user", "content": text})
        streamer = Streamer(bot, chat_id, emoji)
        await streamer.start("💭 Думаю…" if kind == "reasoner" else "✨ Печатаю…")

        answer, last_edit, reasoning_chars = "", 0.0, 0
        try:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            async for part, chunk in ai.stream(history, role, kind):
                if part == "reasoning":
                    reasoning_chars += len(chunk)
                    continue
                answer += chunk
                now = time.monotonic()
                if now - last_edit >= EDIT_INTERVAL:
                    last_edit = now
                    await streamer.update(answer)
        except RateLimitError:
            return await _fail(streamer, answer, "⏳ DeepSeek просит притормозить. Попробуй через минуту.")
        except APIConnectionError:
            return await _fail(streamer, answer, "🌐 Не удалось связаться с DeepSeek. Попробуй ещё раз.")
        except APIStatusError as e:
            log.error("DeepSeek error %s: %s", e.status_code, e.message)
            hint = "💳 Проверь баланс/ключ DeepSeek." if e.status_code in (401, 402) else "⚠️ Ошибка DeepSeek."
            return await _fail(streamer, answer, f"{hint} (код {e.status_code})")
        except Exception:  # noqa: BLE001
            log.exception("generation failed")
            return await _fail(streamer, answer, "⚠️ Что-то пошло не так. Попробуй ещё раз.")

        answer = answer.strip() or "🤔 Пустой ответ, попробуй переформулировать."
        await streamer.update(answer, final=True, markup=after_answer_kb())
        await db.add_messages(chat_id, ("user", text), ("assistant", answer))
        await db.count_request(user_id)


async def _fail(streamer: Streamer, partial: str, msg: str) -> None:
    if partial.strip():
        await streamer.update(partial + "\n\n" + msg, final=True)
    elif streamer.msgs:
        await streamer._edit(0, B(msg), msg)  # noqa: SLF001
    else:
        await streamer.bot.send_message(streamer.chat_id, B(msg))


@router.callback_query(F.data == "regen")
async def cb_regen(c: CallbackQuery, bot: Bot):
    if _locks[c.message.chat.id].locked():
        return await c.answer("Я ещё отвечаю…")
    prev = await db.pop_last_exchange(c.message.chat.id)
    if not prev:
        return await c.answer("Нечего перегенерировать", show_alert=True)
    await c.answer("Генерирую заново…")
    await c.message.edit_reply_markup(reply_markup=None)
    await respond(bot, c.message.chat.id, c.from_user.id, prev)


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(m: Message, bot: Bot):
    await respond(bot, m.chat.id, m.from_user.id, m.text)


@router.message()
async def on_other(m: Message):
    await m.answer(B("📎 Пока я понимаю только текст. Напиши вопрос словами!"))

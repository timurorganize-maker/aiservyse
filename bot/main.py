import asyncio
import logging
import time
from collections import defaultdict

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (BotCommand, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)
from anthropic import AsyncAnthropic

from . import config
from .formatting import split_message, to_html

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aibot")

router = Router()
ai = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

history: dict[int, list[dict]] = defaultdict(list)
persona: dict[int, str] = defaultdict(lambda: "assistant")
busy: set[int] = set()


def allowed(uid: int) -> bool:
    return not config.ALLOWED or uid in config.ALLOWED


def main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎭 Сменить роль", callback_data="roles"),
         InlineKeyboardButton(text="🧹 Новый диалог", callback_data="new")],
    ])


def roles_kb(current: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=("✅ " if k == current else "") + name, callback_data=f"role:{k}")]
        for k, (name, _) in config.PERSONAS.items()]
    rows.append([InlineKeyboardButton(text="‹ Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


WELCOME = (
    "<b>Привет, {name}! 👋</b>\n\n"
    "Я — твой ИИ-собеседник на базе <b>Claude</b>.\n"
    "Отвечаю на вопросы, пишу код и тексты, перевожу, объясняю сложное.\n\n"
    "✨ <b>Что умею</b>\n"
    "• помню контекст разговора\n"
    "• меняю роль: программист, учитель, писатель…\n"
    "• красиво оформляю код и списки\n\n"
    "Просто напиши мне сообщение 👇"
)


@router.message(CommandStart())
async def start(m: Message):
    if not allowed(m.from_user.id):
        return await m.answer("🔒 Бот приватный.")
    await m.answer(WELCOME.format(name=m.from_user.first_name), reply_markup=main_kb())


@router.message(Command("help"))
async def help_(m: Message):
    await m.answer(
        "<b>Команды</b>\n/new — начать новый диалог\n/role — выбрать роль\n/help — эта справка",
        reply_markup=main_kb())


@router.message(Command("new"))
async def new(m: Message):
    history[m.from_user.id].clear()
    await m.answer("🧹 Контекст очищен. Начнём с чистого листа!")


@router.message(Command("role"))
async def role(m: Message):
    await m.answer("🎭 <b>Выбери роль:</b>", reply_markup=roles_kb(persona[m.from_user.id]))


@router.callback_query(F.data == "roles")
async def cb_roles(c: CallbackQuery):
    await c.message.edit_text("🎭 <b>Выбери роль:</b>", reply_markup=roles_kb(persona[c.from_user.id]))
    await c.answer()


@router.callback_query(F.data.startswith("role:"))
async def cb_role(c: CallbackQuery):
    key = c.data.split(":", 1)[1]
    if key in config.PERSONAS:
        persona[c.from_user.id] = key
        history[c.from_user.id].clear()
    await c.message.edit_text(
        f"Роль: <b>{config.PERSONAS[persona[c.from_user.id]][0]}</b>\nКонтекст сброшен — пиши!",
        reply_markup=main_kb())
    await c.answer("Готово")


@router.callback_query(F.data == "back")
async def cb_back(c: CallbackQuery):
    await c.message.edit_text("Готов к общению 👇", reply_markup=main_kb())
    await c.answer()


@router.callback_query(F.data == "new")
async def cb_new(c: CallbackQuery):
    history[c.from_user.id].clear()
    await c.answer("🧹 Контекст очищен", show_alert=False)


async def typing_loop(m: Message, stop: asyncio.Event):
    while not stop.is_set():
        try:
            await m.bot.send_chat_action(m.chat.id, ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), 4)
        except asyncio.TimeoutError:
            pass


async def safe_edit(msg: Message, text: str, html_mode: bool = True):
    try:
        if html_mode:
            await msg.edit_text(to_html(text) or "…", parse_mode=ParseMode.HTML)
        else:
            await msg.edit_text(text or "…", parse_mode=None)
    except TelegramBadRequest as e:
        if "not modified" in str(e):
            return
        if html_mode:  # битая разметка в недописанном ответе — пробуем без неё
            await safe_edit(msg, text, html_mode=False)


@router.message(F.text & ~F.text.startswith("/"))
async def chat(m: Message):
    uid = m.from_user.id
    if not allowed(uid):
        return await m.answer("🔒 Бот приватный.")
    if uid in busy:
        return await m.answer("⏳ Подожди, я ещё отвечаю на предыдущее сообщение.")
    busy.add(uid)
    stop = asyncio.Event()
    typing = asyncio.create_task(typing_loop(m, stop))
    hist = history[uid]
    hist.append({"role": "user", "content": m.text})
    del hist[:-config.MAX_HISTORY]
    while hist and hist[0]["role"] != "user":
        hist.pop(0)

    sent = await m.answer("💭 Думаю…")
    full, last_edit = "", 0.0
    try:
        async with ai.messages.stream(
            model=config.MODEL, max_tokens=4096,
            system=config.PERSONAS[persona[uid]][1] + " Форматируй ответ в Markdown.",
            messages=hist,
        ) as stream:
            async for chunk in stream.text_stream:
                full += chunk
                now = time.monotonic()
                if now - last_edit > 1.2 and len(full) < 3800:
                    last_edit = now
                    await safe_edit(sent, full + " ▌")
        hist.append({"role": "assistant", "content": full})

        parts = split_message(full)
        await safe_edit(sent, parts[0])
        for p in parts[1:]:
            try:
                await m.answer(to_html(p), parse_mode=ParseMode.HTML)
            except TelegramBadRequest:
                await m.answer(p, parse_mode=None)
    except Exception as e:
        log.exception("AI error")
        hist.pop()  # убираем вопрос без ответа
        await safe_edit(sent, f"⚠️ Не получилось получить ответ: {type(e).__name__}. Попробуй ещё раз.", False)
    finally:
        stop.set()
        typing.cancel()
        busy.discard(uid)


@router.message()
async def other(m: Message):
    await m.answer("Пока я понимаю только текст ✍️")


async def run():
    if not config.BOT_TOKEN or not config.ANTHROPIC_API_KEY:
        raise SystemExit("Заполни TELEGRAM_BOT_TOKEN и ANTHROPIC_API_KEY в .env")
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.set_my_commands([
        BotCommand(command="new", description="🧹 Новый диалог"),
        BotCommand(command="role", description="🎭 Выбрать роль"),
        BotCommand(command="help", description="❓ Помощь"),
    ])
    dp = Dispatcher()
    dp.include_router(router)
    log.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())

# DeepSeek Telegram Bot

Полноценный ИИ-бот для Telegram на **DeepSeek API** (aiogram 3).

## Возможности
- 💬 Диалог с памятью (SQLite), `/new` — сброс
- ⚡ Стриминг ответа в реальном времени (живое редактирование сообщения)
- 🎨 Красивое оформление: Markdown → Telegram HTML (жирный/курсив, списки, заголовки, цитаты, ссылки, код с подсветкой, таблицы)
- ✂️ Длинные ответы режутся на сообщения, не ломая блоки кода
- 🎭 `/role` — 6 ролей (ассистент, программист, копирайтер, переводчик, учитель, аналитик)
- 🧠 `/model` — быстрая `deepseek-chat` или думающая `deepseek-reasoner`
- 🔄 Кнопки «Заново» и «Новый диалог» под ответом
- 🔒 Белый список пользователей, админы
- 💎 Премиум-эмодзи (см. ниже)

## Запуск
```bash
pip install -r requirements.txt
cp .env.example .env   # TELEGRAM_BOT_TOKEN от @BotFather, DEEPSEEK_API_KEY с platform.deepseek.com
python -m bot.main
```
или `docker compose up -d --build`.

## Премиум-эмодзи
Бот заменяет обычные эмодзи (и в интерфейсе, и в ответах ИИ) на кастомные через `<tg-emoji>`.
1. Укажи свой Telegram ID в `ADMIN_IDS`.
2. Отправь боту `/emojipack https://t.me/addemoji/НазваниеНабора` — все эмодзи набора привяжутся
   к своим обычным аналогам и сохранятся в БД.
3. `PREMIUM_EMOJI=auto` — включаются, когда админ с Telegram Premium напишет боту
   (`on`/`off` — принудительно). Статус смотри в `/status`.

Если Telegram не разрешит боту кастомные эмодзи, пользователь увидит обычные — ничего не ломается.
Помощники: `/emojiid` (ответом на сообщение с эмодзи покажет id), `/emojireset`.

## Тесты
```bash
pip install -r requirements-dev.txt && pytest
```

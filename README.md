# DeepSeek Telegram Bot (Vercel + Supabase)

ИИ-бот для Telegram на **DeepSeek API**: стриминг ответов, красивое оформление, память диалога,
роли, режим рассуждений и премиум-эмодзи. Работает на Vercel (webhook), данные — в Supabase.

## Деплой
1. **Supabase** → New project → SQL Editor → вставь и выполни `supabase/schema.sql`.
   Ключи: Project Settings → API → `Project URL` и `service_role` key.
2. **Telegram**: создай бота в @BotFather, возьми токен. Свой ID узнай у @userinfobot.
3. **Vercel** → Add New Project → импортируй этот репозиторий → в Environment Variables добавь
   переменные из `.env.example` (обязательные: `TELEGRAM_BOT_TOKEN`, `DEEPSEEK_API_KEY`,
   `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `WEBHOOK_SECRET`; рекомендуется `ADMIN_IDS`) → Deploy.
4. Открой в браузере один раз:
   `https://<твой-проект>.vercel.app/api/setup?secret=<WEBHOOK_SECRET>`
   — установит webhook и меню команд. Напиши боту `/start`.

> `maxDuration` в `vercel.json` = 300 с (нужен Fluid Compute, включён по умолчанию на новых проектах).
> На старом Hobby-плане лимит 60 с — поставь 60, если деплой ругнётся.

## Премиум-эмодзи
1. `ADMIN_IDS` = твой Telegram ID.
2. Боту: `/emojipack https://t.me/addemoji/НазваниеНабора` — эмодзи набора привяжутся к обычным.
3. `PREMIUM_EMOJI=auto` включит их, когда админ с Telegram Premium напишет боту (`on`/`off` — принудительно).
Если Telegram не разрешит — увидишь обычные эмодзи, ничего не ломается. Статус: `/status`.

## Локальная разработка
```bash
pip install -r requirements.txt && cp .env.example .env
python -m bot.main        # long polling (сам снимет webhook)
pip install -r requirements-dev.txt && pytest
```

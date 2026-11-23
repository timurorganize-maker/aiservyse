# AI Telegram Bot

Красивый ИИ-бот для Telegram (aiogram 3 + Claude): стриминг ответа, память диалога,
выбор роли, оформление кода и списков.

## Запуск
```bash
pip install -r requirements.txt
cp .env.example .env   # впиши TELEGRAM_BOT_TOKEN и ANTHROPIC_API_KEY
python -m bot.main
```
Команды: `/new` — новый диалог, `/role` — роль, `/help`.
`.env` в git не попадает.

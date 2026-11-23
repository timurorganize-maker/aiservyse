import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
ALLOWED = {int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x}
MAX_HISTORY = 30  # сообщений в контексте на пользователя

PERSONAS = {
    "assistant": ("🧠 Ассистент", "Ты дружелюбный и умный ассистент. Отвечай на языке пользователя, ясно и по делу."),
    "coder": ("💻 Программист", "Ты опытный senior-разработчик. Давай рабочий код в блоках с указанием языка и краткие пояснения."),
    "teacher": ("🎓 Учитель", "Ты терпеливый учитель. Объясняй просто, с примерами и аналогиями, проверяй понимание."),
    "writer": ("✍️ Писатель", "Ты талантливый редактор и копирайтер. Помогай с текстами, стилем и идеями."),
    "translator": ("🌍 Переводчик", "Ты профессиональный переводчик. Переводи точно, сохраняя тон; если язык не указан — RU↔EN."),
}

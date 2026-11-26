from __future__ import annotations

from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from .config import Config

ROLES: dict[str, tuple[str, str]] = {
    "assistant": ("🤖 Ассистент", "Ты — умный, дружелюбный и точный ИИ-ассистент."),
    "coder": (
        "💻 Программист",
        "Ты — опытный senior-разработчик. Давай рабочий, лаконичный код с краткими пояснениями, "
        "указывай язык в блоках кода, упоминай крайние случаи.",
    ),
    "writer": ("✍️ Копирайтер", "Ты — талантливый редактор и копирайтер. Пиши живо, образно и без воды."),
    "translator": (
        "🌍 Переводчик",
        "Ты — профессиональный переводчик. Переводи точно, сохраняя стиль. Если язык не указан: "
        "русский переводи на английский, остальные — на русский. Выдавай только перевод.",
    ),
    "teacher": (
        "🎓 Учитель",
        "Ты — терпеливый преподаватель. Объясняй просто, с примерами и аналогиями, шаг за шагом.",
    ),
    "analyst": (
        "📊 Аналитик",
        "Ты — аналитик. Структурируй мысли, взвешивай аргументы, приводи выводы и риски.",
    ),
}

STYLE = (
    "Отвечай на языке пользователя. Оформляй ответ в Markdown: **жирный** для ключевого, списки, "
    "заголовки ## только для длинных ответов, код — в тройных кавычках с указанием языка, "
    "цитаты через >. Таблицы не используй — вместо них списки. Уместно и умеренно добавляй эмодзи. "
    "Будь краток, если не просят подробностей."
)


def system_prompt(role: str) -> str:
    return f"{ROLES.get(role, ROLES['assistant'])[1]}\n\n{STYLE}"


class DeepSeek:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = AsyncOpenAI(api_key=cfg.deepseek_key, base_url=cfg.deepseek_base_url, max_retries=2, timeout=120)

    def model_name(self, kind: str) -> str:
        return self.cfg.reasoner_model if kind == "reasoner" else self.cfg.model

    async def stream(self, history: list[dict], role: str, kind: str) -> AsyncIterator[tuple[str, str]]:
        """Отдаёт пары ('reasoning'|'content', текст)."""
        messages = [{"role": "system", "content": system_prompt(role)}, *history]
        kwargs = {} if kind == "reasoner" else {"temperature": self.cfg.temperature}
        resp = await self.client.chat.completions.create(
            model=self.model_name(kind), messages=messages, max_tokens=self.cfg.max_tokens, stream=True, **kwargs
        )
        async for chunk in resp:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if reasoning := getattr(delta, "reasoning_content", None):
                yield "reasoning", reasoning
            if delta.content:
                yield "content", delta.content

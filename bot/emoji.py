"""Премиум (custom) эмодзи: подмена обычных эмодзи на <tg-emoji> в готовом HTML.

Если у бота нет права на кастомные эмодзи, Telegram просто покажет обычный эмодзи-fallback,
поэтому подмена безопасна в любом случае.
"""
from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"(<pre.*?</pre>|<code>.*?</code>|<[^>]+>)", re.S)
_VS16 = "️"


def norm(e: str) -> str:
    return e.replace(_VS16, "")


class PremiumEmoji:
    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}
        self.enabled = True
        self._rx: re.Pattern | None = None

    def update(self, mapping: dict[str, str]) -> None:
        self.mapping.update({norm(k): v for k, v in mapping.items()})
        self._rebuild()

    def clear(self) -> None:
        self.mapping.clear()
        self._rebuild()

    def _rebuild(self) -> None:
        keys = sorted(self.mapping, key=len, reverse=True)
        self._rx = re.compile("(" + "|".join(re.escape(k) for k in keys) + ")" + _VS16 + "?") if keys else None

    def apply(self, html_text: str) -> str:
        if not (self.enabled and self._rx):
            return html_text
        rx = self._rx
        parts = _TOKEN_RE.split(html_text)
        for i in range(0, len(parts), 2):  # чётные — обычный текст, нечётные — теги/код
            parts[i] = rx.sub(
                lambda m: f'<tg-emoji emoji-id="{self.mapping[m.group(1)]}">{m.group(0)}</tg-emoji>', parts[i]
            )
        return "".join(parts)

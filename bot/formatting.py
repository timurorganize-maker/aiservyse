"""Конвертер Markdown (как пишет ИИ) в безопасный Telegram HTML."""
import html
import re

_CODE_BLOCK = re.compile(r"```(\w+)?\n?(.*?)```", re.S)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\*\w])")
_HEADER = re.compile(r"^#{1,6}\s+(.+)$", re.M)
_LIST = re.compile(r"^(\s*)[-*]\s+", re.M)
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def to_html(text: str) -> str:
    stash: list[str] = []

    def keep(s: str) -> str:
        stash.append(s)
        return f"\x00{len(stash) - 1}\x00"

    def code_block(m: re.Match) -> str:
        lang, body = m.group(1), html.escape(m.group(2).rstrip("\n"))
        cls = f' class="language-{lang}"' if lang else ""
        return keep(f"<pre><code{cls}>{body}</code></pre>")

    text = _CODE_BLOCK.sub(code_block, text)
    text = _INLINE_CODE.sub(lambda m: keep(f"<code>{html.escape(m.group(1))}</code>"), text)
    text = html.escape(text, quote=False)
    text = _HEADER.sub(r"<b>\1</b>", text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    text = _LINK.sub(r'<a href="\2">\1</a>', text)
    text = _LIST.sub(r"\1• ", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], text)


def split_message(text: str, limit: int = 3800) -> list[str]:
    """Режем длинный ответ по абзацам/строкам, чтобы влезть в лимит Telegram."""
    parts: list[str] = []
    while len(text) > limit:
        cut = max(text.rfind("\n\n", 0, limit), text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts

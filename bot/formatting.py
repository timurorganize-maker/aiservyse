"""Markdown (как его пишет LLM) -> Telegram HTML, плюс безопасная нарезка длинных ответов."""
from __future__ import annotations

import html
import re

FENCE_RE = re.compile(r"```([\w+#.\-]*)[ \t]*\n(.*?)(?:```|\Z)", re.S)
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)\"<>]+)\)")
BARE_URL_RE = re.compile(r"https?://[^\s<>\"]+")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
HR_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
NUMBERED_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
QUOTE_RE = re.compile(r"^&gt;\s?(.*)$")
PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")

BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
ITALIC_STAR_RE = re.compile(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])")
ITALIC_UND_RE = re.compile(r"(?<![\w_])_(?![\s_])(.+?)(?<![\s_])_(?![\w_])")
STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
SPOILER_RE = re.compile(r"\|\|(?=\S)(.+?)(?<=\S)\|\|")


def md_to_html(md: str) -> str:
    stash: list[str] = []

    def keep(s: str) -> str:
        stash.append(s)
        return f"\x00{len(stash) - 1}\x00"

    def fence(m: re.Match) -> str:
        lang, code = m.group(1), html.escape(m.group(2).rstrip("\n"), quote=False)
        if lang:
            return keep(f'<pre><code class="language-{lang}">{code}</code></pre>')
        return keep(f"<pre>{code}</pre>")

    text = FENCE_RE.sub(fence, md)

    # markdown-таблицы -> моноширинный блок
    lines, buf, tmp = text.split("\n"), [], []

    def flush_table() -> None:
        if len(tmp) >= 2:
            buf.append(keep("<pre>" + html.escape("\n".join(tmp), quote=False) + "</pre>"))
        else:
            buf.extend(tmp)
        tmp.clear()

    for ln in lines:
        if TABLE_ROW_RE.match(ln):
            tmp.append(ln.strip())
        else:
            flush_table()
            buf.append(ln)
    flush_table()
    text = "\n".join(buf)

    text = INLINE_CODE_RE.sub(lambda m: keep(f"<code>{html.escape(m.group(1), quote=False)}</code>"), text)
    text = html.escape(text, quote=False)

    def link(m: re.Match) -> str:
        return keep(f'<a href="{m.group(2)}">') + m.group(1) + keep("</a>")

    def bare(m: re.Match) -> str:
        url = m.group(0)
        tail = ""
        while url and url[-1] in ".,;:!?)":
            tail, url = url[-1] + tail, url[:-1]
        return keep(url) + tail

    def inline(s: str) -> str:
        s = LINK_RE.sub(link, s)
        s = BARE_URL_RE.sub(bare, s)
        s = BOLD_RE.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", s)
        s = ITALIC_STAR_RE.sub(r"<i>\1</i>", s)
        s = ITALIC_UND_RE.sub(r"<i>\1</i>", s)
        s = STRIKE_RE.sub(r"<s>\1</s>", s)
        return SPOILER_RE.sub(r"<tg-spoiler>\1</tg-spoiler>", s)

    out: list[str] = []
    quote: list[str] = []

    def flush_quote() -> None:
        if quote:
            tag = "<blockquote expandable>" if len(quote) > 6 else "<blockquote>"
            out.append(f"{tag}{chr(10).join(quote)}</blockquote>")
            quote.clear()

    for line in text.split("\n"):
        if m := QUOTE_RE.match(line):
            quote.append(inline(m.group(1)))
            continue
        flush_quote()
        if HR_RE.match(line):
            out.append("──────────")
        elif m := HEADER_RE.match(line):
            out.append(f"<b>{inline(m.group(1))}</b>")
        elif m := BULLET_RE.match(line):
            depth = len(m.group(1).replace("\t", "  ")) // 2
            out.append(" " * depth + ("•" if depth == 0 else "◦") + " " + inline(m.group(2)))
        elif m := NUMBERED_RE.match(line):
            depth = len(m.group(1).replace("\t", "  ")) // 2
            out.append(" " * depth + f"{m.group(2)}. " + inline(m.group(3)))
        else:
            out.append(inline(line))
    flush_quote()

    return PLACEHOLDER_RE.sub(lambda m: stash[int(m.group(1))], "\n".join(out)).strip()


def split_markdown(text: str, limit: int = 3200) -> list[str]:
    """Режет markdown на куски <= limit, не ломая ``` блоки."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    fence_lang: str | None = None  # None — мы вне блока кода

    def close() -> None:
        nonlocal cur, size
        body = "\n".join(cur)
        if fence_lang is not None:
            body += "\n```"
        chunks.append(body)
        cur = [f"```{fence_lang}"] if fence_lang is not None else []
        size = sum(len(x) + 1 for x in cur)

    for line in text.split("\n"):
        while len(line) > limit - 20:  # очень длинная строка
            head, line = line[: limit - 20], line[limit - 20 :]
            if size + len(head) + 1 > limit and cur:
                close()
            cur.append(head)
            size += len(head) + 1
        if size + len(line) + 1 > limit and cur:
            close()
        cur.append(line)
        size += len(line) + 1
        stripped = line.strip()
        if stripped.startswith("```"):
            fence_lang = None if fence_lang is not None else stripped[3:].strip()
    if "\n".join(cur).strip():
        chunks.append("\n".join(cur))
    return [c for c in chunks if c.strip()] or [""]

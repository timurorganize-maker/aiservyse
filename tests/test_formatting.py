from bot.emoji import PremiumEmoji
from bot.formatting import md_to_html, split_markdown


def test_basic_inline():
    assert md_to_html("**жирный** и *курсив* и ~~зачёркнут~~") == "<b>жирный</b> и <i>курсив</i> и <s>зачёркнут</s>"


def test_escape_html():
    assert md_to_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"


def test_code_block_protected():
    out = md_to_html("```python\nx = '**no**' < 1\n```")
    assert out == '<pre><code class="language-python">x = \'**no**\' &lt; 1</code></pre>'


def test_unclosed_fence_while_streaming():
    assert md_to_html("текст\n```js\nlet a").endswith("<pre><code class=\"language-js\">let a</code></pre>")


def test_inline_code_and_underscores():
    out = md_to_html("`snake_case_var` и snake_case_word")
    assert "<code>snake_case_var</code>" in out and "<i>" not in out


def test_lists_headers_quote_link():
    out = md_to_html("## Заголовок\n- один\n  - вложенный\n1. раз\n> цитата\n[сайт](https://a.b/c_d_e)")
    assert "<b>Заголовок</b>" in out
    assert "• один" in out and "◦ вложенный" in out and "1. раз" in out
    assert "<blockquote>цитата</blockquote>" in out
    assert '<a href="https://a.b/c_d_e">сайт</a>' in out


def test_table_to_pre():
    assert md_to_html("| a | b |\n|---|---|\n| 1 | 2 |").startswith("<pre>| a | b |")


def test_split_keeps_fences_balanced():
    text = "```py\n" + "\n".join(f"line {i}" for i in range(400)) + "\n```"
    chunks = split_markdown(text, 500)
    assert len(chunks) > 1
    for c in chunks:
        assert c.count("```") % 2 == 0 and len(c) <= 560


def test_premium_emoji_skips_code():
    pe = PremiumEmoji()
    pe.update({"🔥": "123"})
    out = pe.apply("🔥 <code>🔥</code> <b>🔥</b>")
    assert out.count("<tg-emoji") == 2 and "<code>🔥</code>" in out
    pe.enabled = False
    assert pe.apply("🔥") == "🔥"

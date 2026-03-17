from __future__ import annotations

from nonebot_plugin_codex.telegram_rendering import render_telegram_html


def test_render_telegram_html_converts_bold() -> None:
    assert render_telegram_html("**bold**") == "<b>bold</b>"


def test_render_telegram_html_converts_italic() -> None:
    assert render_telegram_html("*italic*") == "<i>italic</i>"


def test_render_telegram_html_converts_inline_code() -> None:
    assert render_telegram_html("use `ls -la`") == "use <code>ls -la</code>"


def test_render_telegram_html_converts_fenced_code_block() -> None:
    assert (
        render_telegram_html("```python\nprint('hi')\n```")
        == "<pre>print(&#x27;hi&#x27;)\n</pre>"
    )


def test_render_telegram_html_converts_links() -> None:
    assert (
        render_telegram_html("[OpenAI](https://openai.com)")
        == '<a href="https://openai.com">OpenAI</a>'
    )


def test_render_telegram_html_escapes_plain_text_with_underscores() -> None:
    assert render_telegram_html("/tmp/my_file") == "/tmp/my_file"


def test_render_telegram_html_leaves_unclosed_markdown_as_text() -> None:
    assert render_telegram_html("bad_markdown_") == "bad_markdown_"


def test_render_telegram_html_converts_dash_list_items() -> None:
    assert render_telegram_html("- one\n- two") == "\u2022 one\n\u2022 two"


def test_render_telegram_html_formats_local_file_links_as_readable_references() -> None:
    assert (
        render_telegram_html("[README.md](/home/tt/project/README.md)")
        == "<b>README.md</b>: <code>/home/tt/project/README.md</code>"
    )


def test_render_telegram_html_converts_markdown_table_to_preformatted_block() -> None:
    text = "| Name | Score |\n| --- | ---: |\n| Alice | 1 |\n| Bob | 2 |"
    assert (
        render_telegram_html(text)
        == "<pre>Name | Score\nAlice | 1\nBob | 2</pre>"
    )


def test_render_telegram_html_converts_headings_to_bold_lines() -> None:
    assert (
        render_telegram_html("# 一级标题\n## 二级标题\n### 三级标题")
        == "<b>一级标题</b>\n<b>二级标题</b>\n<b>三级标题</b>"
    )


def test_render_telegram_html_converts_thematic_break_to_separator() -> None:
    assert render_telegram_html("before\n---\nafter") == "before\n──────────\nafter"

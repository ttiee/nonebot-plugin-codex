from __future__ import annotations

import html
import re

FENCED_CODE_PATTERN = re.compile(r"```[^\n`]*\n(.*?)```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`([^`\n]+)`")
LOCAL_LINK_PATTERN = re.compile(r"\[([^\]\n]+)\]\((/[^)\n]+)\)")
LINK_PATTERN = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
BOLD_ASTERISK_PATTERN = re.compile(r"(?<!\*)\*\*(?=\S)(.+?)(?<=\S)\*\*(?!\*)")
BOLD_UNDERSCORE_PATTERN = re.compile(r"(?<!_)__(?=\S)(.+?)(?<=\S)__(?!_)")
ITALIC_ASTERISK_PATTERN = re.compile(r"(?<!\*)\*(?=\S)(.+?)(?<=\S)\*(?!\*)")
ITALIC_UNDERSCORE_PATTERN = re.compile(r"(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])")
LIST_ITEM_PATTERN = re.compile(r"^(\s*)[-*]\s+(.*)$")
TOKEN_TEMPLATE = "\x00TGHTML{index}\x00"


def _stash(tokens: list[str], value: str) -> str:
    token = TOKEN_TEMPLATE.format(index=len(tokens))
    tokens.append(value)
    return token


def _restore_tokens(text: str, tokens: list[str]) -> str:
    for index, value in enumerate(tokens):
        text = text.replace(TOKEN_TEMPLATE.format(index=index), value)
    return text


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _is_table_separator(line: str) -> bool:
    stripped = line.strip().strip("|").strip()
    if not stripped:
        return False
    cells = [cell.strip() for cell in stripped.split("|")]
    return all(cell and set(cell) <= {"-", ":"} and "-" in cell for cell in cells)


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _render_blocks(text: str, tokens: list[str]) -> str:
    lines = text.splitlines()
    rendered: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]

        if (
            index + 1 < len(lines)
            and _is_table_row(line)
            and _is_table_separator(lines[index + 1])
        ):
            table_lines = [_split_table_row(line)]
            index += 2
            while index < len(lines) and _is_table_row(lines[index]):
                table_lines.append(_split_table_row(lines[index]))
                index += 1
            table_text = "\n".join(" | ".join(row) for row in table_lines)
            rendered.append(_stash(tokens, f"<pre>{html.escape(table_text)}</pre>"))
            continue

        match = LIST_ITEM_PATTERN.match(line)
        if match is not None:
            indent, content = match.groups()
            rendered.append(f"{indent}\u2022 {content}")
            index += 1
            continue

        rendered.append(line)
        index += 1

    return "\n".join(rendered)


def render_telegram_html(text: str) -> str:
    if not text:
        return ""

    tokens: list[str] = []

    text = FENCED_CODE_PATTERN.sub(
        lambda match: _stash(tokens, f"<pre>{html.escape(match.group(1))}</pre>"),
        text,
    )
    text = INLINE_CODE_PATTERN.sub(
        lambda match: _stash(tokens, f"<code>{html.escape(match.group(1))}</code>"),
        text,
    )
    text = _render_blocks(text, tokens)

    text = html.escape(text)
    text = LOCAL_LINK_PATTERN.sub(
        lambda match: (
            f"<b>{match.group(1)}</b>: <code>{match.group(2)}</code>"
        ),
        text,
    )
    text = LINK_PATTERN.sub(
        lambda match: (
            f'<a href="{html.escape(match.group(2), quote=True)}">{match.group(1)}</a>'
        ),
        text,
    )
    text = BOLD_ASTERISK_PATTERN.sub(r"<b>\1</b>", text)
    text = BOLD_UNDERSCORE_PATTERN.sub(r"<b>\1</b>", text)
    text = ITALIC_ASTERISK_PATTERN.sub(r"<i>\1</i>", text)
    text = ITALIC_UNDERSCORE_PATTERN.sub(r"<i>\1</i>", text)
    return _restore_tokens(text, tokens)

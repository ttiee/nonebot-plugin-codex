from __future__ import annotations

from tools.release_notes import (
    ReleaseNoteItem,
    build_compare_url,
    render_release_notes,
)


def test_render_release_notes_groups_conventional_commits() -> None:
    notes = render_release_notes(
        current_tag="v0.1.2",
        previous_tag="v0.1.1",
        repo="ttiee/nonebot-plugin-codex",
        items=[
            ReleaseNoteItem("feat", "telegram", "add release note panel", "abc1234"),
            ReleaseNoteItem("fix", "config", "simplify plugin config storage", "def5678"),
            ReleaseNoteItem("docs", None, "refresh README config section", "9876543"),
            ReleaseNoteItem("chore", None, "prepare release assets", "1357246"),
        ],
    )

    assert "# v0.1.2" in notes
    assert (
        "Compare: https://github.com/ttiee/nonebot-plugin-codex/compare/"
        "v0.1.1...v0.1.2"
    ) in notes
    assert "## Features" in notes
    assert "- `telegram`: add release note panel (`abc1234`)" in notes
    assert "## Fixes" in notes
    assert "- `config`: simplify plugin config storage (`def5678`)" in notes
    assert "## Documentation" in notes
    assert "- refresh README config section (`9876543`)" in notes
    assert "## Chores" in notes


def test_render_release_notes_without_previous_tag_uses_changes_section() -> None:
    notes = render_release_notes(
        current_tag="v0.1.0",
        previous_tag=None,
        repo="ttiee/nonebot-plugin-codex",
        items=[ReleaseNoteItem("other", None, "initial release", "abc1234")],
    )

    assert "Initial release." in notes
    assert "## Changes" in notes
    assert "- initial release (`abc1234`)" in notes
    assert "Compare:" not in notes


def test_build_compare_url_returns_none_without_previous_tag() -> None:
    assert build_compare_url("ttiee/nonebot-plugin-codex", None, "v0.1.2") is None

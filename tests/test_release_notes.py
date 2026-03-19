from __future__ import annotations

import pytest

from tools.release_notes import (
    ReleaseNoteItem,
    build_compare_url,
    collect_release_items,
    parse_commit_subject,
    render_release_notes,
)


def test_render_release_notes_groups_conventional_commits() -> None:
    notes = render_release_notes(
        current_tag="v0.1.2",
        previous_tag="v0.1.1",
        repo="ttiee/nonebot-plugin-codex",
        items=[
            ReleaseNoteItem(
                "feat",
                "telegram",
                "add release note panel",
                "abc1234",
                commit_hash="abc123456789",
                pull_request=42,
            ),
            ReleaseNoteItem(
                "fix",
                "config",
                "simplify plugin config storage",
                "def5678",
                commit_hash="def5678123456",
            ),
            ReleaseNoteItem(
                "docs",
                None,
                "refresh README config section",
                "9876543",
                commit_hash="9876543210abc",
            ),
            ReleaseNoteItem("chore", None, "prepare release assets", "1357246"),
        ],
    )

    assert notes.startswith("Released on ")
    assert "# v0.1.2" not in notes
    assert (
        "Compare: https://github.com/ttiee/nonebot-plugin-codex/compare/"
        "v0.1.1...v0.1.2"
    ) in notes
    assert "## Features" in notes
    feature_line = (
        "- `telegram`: add release note panel "
        "([`abc1234`](https://github.com/ttiee/nonebot-plugin-codex/commit/"
        "abc123456789), "
        "[#42](https://github.com/ttiee/nonebot-plugin-codex/pull/42))"
    )
    assert (
        feature_line in notes
    )
    assert "## Fixes" in notes
    assert (
        "- `config`: simplify plugin config storage "
        "([`def5678`](https://github.com/ttiee/nonebot-plugin-codex/commit/def5678123456))"
    ) in notes
    assert "## Documentation" in notes
    assert (
        "- refresh README config section "
        "([`9876543`](https://github.com/ttiee/nonebot-plugin-codex/commit/9876543210abc))"
    ) in notes
    assert "## Chores" in notes


def test_render_release_notes_without_previous_tag_uses_changes_section() -> None:
    notes = render_release_notes(
        current_tag="v0.1.0",
        previous_tag=None,
        repo="ttiee/nonebot-plugin-codex",
        items=[
            ReleaseNoteItem(
                "other",
                None,
                "initial release",
                "abc1234",
                commit_hash="abc123456789",
            )
        ],
    )

    assert "Initial release." in notes
    assert "## Changes" in notes
    assert (
        "- initial release "
        "([`abc1234`](https://github.com/ttiee/nonebot-plugin-codex/commit/abc123456789))"
    ) in notes
    assert "Compare:" not in notes


def test_build_compare_url_returns_none_without_previous_tag() -> None:
    assert build_compare_url("ttiee/nonebot-plugin-codex", None, "v0.1.2") is None


def test_parse_commit_subject_supports_breaking_changes_and_pr_numbers() -> None:
    item = parse_commit_subject(
        "feat(telegram)!: add typing indicator (#42)",
        short_hash="abc1234",
        commit_hash="abc123456789",
    )

    assert item == ReleaseNoteItem(
        "feat",
        "telegram",
        "add typing indicator",
        "abc1234",
        commit_hash="abc123456789",
        pull_request=42,
        breaking=True,
    )


def test_render_release_notes_promotes_breaking_changes() -> None:
    notes = render_release_notes(
        current_tag="v0.2.0",
        previous_tag="v0.1.9",
        repo="ttiee/nonebot-plugin-codex",
        items=[
            ReleaseNoteItem(
                "feat",
                "telegram",
                "drop legacy command flow",
                "abc1234",
                commit_hash="abc123456789",
                pull_request=9,
                breaking=True,
            ),
            ReleaseNoteItem(
                "fix",
                "service",
                "stabilize retry handling",
                "def5678",
                commit_hash="def5678123456",
            ),
        ],
    )

    assert "## Breaking Changes" in notes
    breaking_line = (
        "- `telegram`: drop legacy command flow "
        "([`abc1234`](https://github.com/ttiee/nonebot-plugin-codex/commit/"
        "abc123456789), "
        "[#9](https://github.com/ttiee/nonebot-plugin-codex/pull/9))"
    )
    assert (
        breaking_line in notes
    )
    assert "## Features" not in notes
    assert "## Fixes" in notes


def test_collect_release_items_skips_release_noise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_git(args: list[str]) -> str:
        assert args == ["log", "--no-merges", "--format=%H%x09%h%x09%s", "v0.1.1..v0.1.2"]
        return "\n".join(
            [
                "111111111111\t1111111\tchore(release): v0.1.2",
                "222222222222\t2222222\tbuild: bump version to 0.1.2",
                "333333333333\t3333333\tchore: release v0.1.2",
                "444444444444\t4444444\tfeat(telegram): add typing indicator (#42)",
            ]
        )

    monkeypatch.setattr("tools.release_notes.run_git", fake_run_git)

    items = collect_release_items("v0.1.2", "v0.1.1")

    assert items == [
        ReleaseNoteItem(
            "feat",
            "telegram",
            "add typing indicator",
            "4444444",
            commit_hash="444444444444",
            pull_request=42,
        )
    ]

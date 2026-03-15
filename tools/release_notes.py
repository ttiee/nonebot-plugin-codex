from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SECTION_TITLES = {
    "feat": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "refactor": "Refactors",
    "docs": "Documentation",
    "test": "Tests",
    "build": "Build",
    "ci": "CI",
    "chore": "Chores",
    "other": "Changes",
}
SECTION_ORDER = [
    "feat",
    "fix",
    "perf",
    "refactor",
    "docs",
    "test",
    "build",
    "ci",
    "chore",
    "other",
]


@dataclass(frozen=True, slots=True)
class ReleaseNoteItem:
    section: str
    scope: str | None
    description: str
    short_hash: str


def run_git(args: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def list_version_tags() -> list[str]:
    output = run_git(["tag", "--sort=version:refname", "--list", "v*"])
    return [line for line in output.splitlines() if line]


def find_previous_tag(current_tag: str) -> str | None:
    tags = list_version_tags()
    try:
        index = tags.index(current_tag)
    except ValueError:
        return tags[-1] if tags else None
    if index == 0:
        return None
    return tags[index - 1]


def parse_commit_subject(subject: str) -> tuple[str, str | None, str]:
    if ": " not in subject:
        return "other", None, subject

    prefix, description = subject.split(": ", 1)
    prefix = prefix.removesuffix("!")
    if "(" in prefix and prefix.endswith(")"):
        commit_type, scope = prefix[:-1].split("(", 1)
        return normalize_section(commit_type), scope, description
    return normalize_section(prefix), None, description


def normalize_section(commit_type: str) -> str:
    return commit_type if commit_type in SECTION_TITLES else "other"


def collect_release_items(
    current_tag: str, previous_tag: str | None
) -> list[ReleaseNoteItem]:
    revision_range = (
        current_tag if previous_tag is None else f"{previous_tag}..{current_tag}"
    )
    output = run_git(
        [
            "log",
            "--no-merges",
            "--format=%h%x09%s",
            revision_range,
        ]
    )
    items: list[ReleaseNoteItem] = []
    for line in output.splitlines():
        if not line:
            continue
        short_hash, subject = line.split("\t", 1)
        section, scope, description = parse_commit_subject(subject)
        items.append(ReleaseNoteItem(section, scope, description, short_hash))
    items.reverse()
    return items


def build_compare_url(
    repo: str, previous_tag: str | None, current_tag: str
) -> str | None:
    if previous_tag is None:
        return None
    return f"https://github.com/{repo}/compare/{previous_tag}...{current_tag}"


def render_release_notes(
    *,
    current_tag: str,
    previous_tag: str | None,
    repo: str,
    items: Sequence[ReleaseNoteItem],
) -> str:
    # lines = [f"# {current_tag}", ""]
    # 去掉重复的版本标题
    lines = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines.append(f"Released on {timestamp}.")
    compare_url = build_compare_url(repo, previous_tag, current_tag)
    if previous_tag is None:
        lines.append("Initial release.")
    else:
        lines.append(f"Changes since `{previous_tag}`.")
    if compare_url:
        lines.append(f"Compare: {compare_url}")
    lines.append("")

    grouped: dict[str, list[ReleaseNoteItem]] = {section: [] for section in SECTION_ORDER}
    for item in items:
        grouped[item.section].append(item)

    for section in SECTION_ORDER:
        section_items = grouped[section]
        if not section_items:
            continue
        lines.append(f"## {SECTION_TITLES[section]}")
        lines.append("")
        for item in section_items:
            if item.scope:
                lines.append(
                    f"- `{item.scope}`: {item.description} (`{item.short_hash}`)"
                )
            else:
                lines.append(f"- {item.description} (`{item.short_hash}`)")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-tag", required=True)
    parser.add_argument("--previous-tag")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    previous_tag = args.previous_tag or find_previous_tag(args.current_tag)
    items = collect_release_items(args.current_tag, previous_tag)
    notes = render_release_notes(
        current_tag=args.current_tag,
        previous_tag=previous_tag,
        repo=args.repo,
        items=items,
    )
    Path(args.output).write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()

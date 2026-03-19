from __future__ import annotations

import argparse
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SECTION_TITLES = {
    "breaking": "Breaking Changes",
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
    "breaking",
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
CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\((?P<scope>[^)]+)\))?(?P<breaking>!)?: (?P<description>.+)$"
)
PULL_REQUEST_SUFFIX_PATTERN = re.compile(r"^(?P<description>.+?)\s+\(#(?P<pr>\d+)\)$")
VERSION_PATTERN = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


@dataclass(frozen=True, slots=True)
class ReleaseNoteItem:
    section: str
    scope: str | None
    description: str
    short_hash: str
    commit_hash: str | None = None
    pull_request: int | None = None
    breaking: bool = False


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


def extract_pull_request(description: str) -> tuple[str, int | None]:
    match = PULL_REQUEST_SUFFIX_PATTERN.match(description)
    if match is None:
        return description, None
    return match.group("description"), int(match.group("pr"))


def parse_commit_subject(
    subject: str,
    *,
    short_hash: str,
    commit_hash: str,
) -> ReleaseNoteItem:
    match = CONVENTIONAL_COMMIT_PATTERN.match(subject)
    if match is None:
        description, pull_request = extract_pull_request(subject)
        return ReleaseNoteItem(
            section="other",
            scope=None,
            description=description,
            short_hash=short_hash,
            commit_hash=commit_hash,
            pull_request=pull_request,
        )

    description, pull_request = extract_pull_request(match.group("description"))
    return ReleaseNoteItem(
        section=normalize_section(match.group("type")),
        scope=match.group("scope"),
        description=description,
        short_hash=short_hash,
        commit_hash=commit_hash,
        pull_request=pull_request,
        breaking=bool(match.group("breaking")),
    )


def normalize_section(commit_type: str) -> str:
    normalized = commit_type.lower()
    return normalized if normalized in SECTION_TITLES else "other"


def is_release_noise(item: ReleaseNoteItem) -> bool:
    description = item.description.lower().strip()
    if item.scope == "release":
        return True
    if item.section not in {"build", "chore"}:
        return False
    if description.startswith("release "):
        return True
    if description.startswith("prepare release"):
        return True
    if description.startswith("bump version to "):
        return True
    return VERSION_PATTERN.fullmatch(description) is not None


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
            "--format=%H%x09%h%x09%s",
            revision_range,
        ]
    )
    items: list[ReleaseNoteItem] = []
    for line in output.splitlines():
        if not line:
            continue
        commit_hash, short_hash, subject = line.split("\t", 2)
        item = parse_commit_subject(
            subject,
            short_hash=short_hash,
            commit_hash=commit_hash,
        )
        if is_release_noise(item):
            continue
        items.append(item)
    items.reverse()
    return items


def build_compare_url(
    repo: str, previous_tag: str | None, current_tag: str
) -> str | None:
    if previous_tag is None:
        return None
    return f"https://github.com/{repo}/compare/{previous_tag}...{current_tag}"


def build_commit_url(repo: str, commit_hash: str | None) -> str | None:
    if not commit_hash:
        return None
    return f"https://github.com/{repo}/commit/{commit_hash}"


def build_pull_request_url(repo: str, pull_request: int | None) -> str | None:
    if pull_request is None:
        return None
    return f"https://github.com/{repo}/pull/{pull_request}"


def render_item(repo: str, item: ReleaseNoteItem) -> str:
    prefix = f"`{item.scope}`: " if item.scope else ""
    references: list[str] = []
    commit_url = build_commit_url(repo, item.commit_hash)
    if commit_url:
        references.append(f"[`{item.short_hash}`]({commit_url})")
    else:
        references.append(f"`{item.short_hash}`")
    pull_request_url = build_pull_request_url(repo, item.pull_request)
    if pull_request_url:
        references.append(f"[#{item.pull_request}]({pull_request_url})")
    return f"- {prefix}{item.description} ({', '.join(references)})"


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
        target_section = "breaking" if item.breaking else item.section
        grouped[target_section].append(item)

    for section in SECTION_ORDER:
        section_items = grouped[section]
        if not section_items:
            continue
        lines.append(f"## {SECTION_TITLES[section]}")
        lines.append("")
        for item in section_items:
            lines.append(render_item(repo, item))
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

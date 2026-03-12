from __future__ import annotations

from pathlib import Path

from nonebot_plugin_codex import __plugin_meta__


def test_plugin_metadata_uses_string_adapter_names() -> None:
    assert __plugin_meta__.homepage == "https://github.com/ttiee/nonebot-plugin-codex"
    assert __plugin_meta__.supported_adapters == {"~telegram"}


def test_issue_templates_are_localized_in_chinese() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    bug_template_path = repo_root / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
    bug_template = bug_template_path.read_text(encoding="utf-8")
    feature_template = (
        repo_root / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml"
    ).read_text(encoding="utf-8")

    assert "问题反馈" in bug_template
    assert "功能请求" in feature_template


def test_pull_request_template_is_localized_in_chinese() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    template = (repo_root / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )

    assert "变更摘要" in template
    assert "验证" in template

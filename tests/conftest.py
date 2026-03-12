from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def model_cache_file(tmp_path: Path) -> Path:
    path = tmp_path / "models_cache.json"
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "gpt-5",
                        "display_name": "GPT-5",
                        "visibility": "list",
                        "priority": 1,
                        "default_reasoning_level": "high",
                        "supported_reasoning_levels": [
                            {"effort": "high"},
                            {"effort": "xhigh"},
                        ],
                    },
                    {
                        "slug": "gpt-4.1",
                        "display_name": "GPT-4.1",
                        "visibility": "hidden",
                        "priority": 2,
                        "default_reasoning_level": "medium",
                        "supported_reasoning_levels": [{"effort": "high"}],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def model_cache_with_medium_file(tmp_path: Path) -> Path:
    path = tmp_path / "models_cache_with_medium.json"
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "gpt-5",
                        "display_name": "GPT-5",
                        "visibility": "list",
                        "priority": 1,
                        "default_reasoning_level": "medium",
                        "supported_reasoning_levels": [
                            {"effort": "medium"},
                            {"effort": "high"},
                            {"effort": "xhigh"},
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path

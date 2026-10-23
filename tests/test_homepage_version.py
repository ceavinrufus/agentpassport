"""The homepage badge tracks the core package version."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_BADGE = re.compile(
    r'<span id="ap-version" data-ap-version="([^"]+)">v([^<]+)</span>'
)


def _package_version() -> str:
    path = ROOT / "packages/agentpassport/pyproject.toml"
    with path.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def test_homepage_badge_matches_package_version():
    version = _package_version()
    html = (ROOT / "docs/site/index.html").read_text(encoding="utf-8")
    match = _BADGE.search(html)
    assert match is not None, "homepage is missing the ap-version badge"
    assert match.group(1) == version
    assert match.group(2) == version
    assert "https://pypi.org/pypi/agentpassport/json" in html

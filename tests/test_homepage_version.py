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


def test_homepage_revocation_and_positioning():
    html = (ROOT / "docs/site/index.html").read_text(encoding="utf-8")
    assert "authorization layer" not in html.lower()
    assert "killing in-flight work" not in html
    assert "Next hop is denied" not in html
    assert "next request denies" not in html
    assert "verify_auth_chain" in html
    assert "Agent.handle" in html
    assert "lucide@latest" not in html
    assert "lucide@1.61.0/dist/umd/lucide.min.js" in html
    assert "sha384-wx1iBc8a89SnsJAxZPb9eNEoMn4t/Wg111+QJyasxB9Om4SDDtkJeBuXx4NiRwa8" in html
    assert 'crossorigin="anonymous"' in html

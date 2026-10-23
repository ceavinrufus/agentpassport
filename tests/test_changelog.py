"""Changelog sections used for GitHub Release notes."""

from pathlib import Path

from scripts.extract_changelog import extract_changelog_section

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_extracts_version_with_or_without_v_prefix():
    plain = extract_changelog_section(CHANGELOG, "0.3.4")
    tagged = extract_changelog_section(CHANGELOG, "v0.3.4")
    assert plain == tagged
    assert plain.startswith("## [0.3.4]")
    assert "max_delegations" in plain
    assert "## [0.3.3]" not in plain


def test_versions_since_0_3_0_are_present():
    for version in ("0.3.4", "0.3.3", "0.3.2"):
        section = extract_changelog_section(CHANGELOG, version)
        assert section.startswith(f"## [{version}]"), version


def test_unknown_version_is_empty():
    assert extract_changelog_section(CHANGELOG, "0.9.9") == ""
    assert extract_changelog_section(CHANGELOG, "v0.9.9") == ""

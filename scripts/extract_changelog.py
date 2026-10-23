"""Pull one version section out of CHANGELOG.md for GitHub Release notes."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SECTION = re.compile(
    r"^## \[(?P<version>[^\]]+)\][^\n]*\n(?P<body>.*?)(?=^## \[|\Z)",
    re.MULTILINE | re.DOTALL,
)


def extract_changelog_section(text: str, version: str) -> str:
    """Return the changelog section for ``version`` (with or without a leading v).

    The returned text includes the ``## [version]`` heading and stops before the
    next version heading. An unknown version returns an empty string.
    """
    wanted = version.removeprefix("v")
    for match in _SECTION.finditer(text):
        if match.group("version") == wanted:
            return match.group(0).strip() + "\n"
    return ""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: extract_changelog.py <version>", file=sys.stderr)
        return 2
    changelog = Path("CHANGELOG.md")
    if not changelog.is_file():
        print("CHANGELOG.md not found", file=sys.stderr)
        return 1
    section = extract_changelog_section(changelog.read_text(encoding="utf-8"), args[0])
    sys.stdout.write(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

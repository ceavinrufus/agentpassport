"""Published package metadata that PyPI and npm render on the project page."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HOMEPAGE = "https://agentpassport.fyi"
REPOSITORY = "https://github.com/ceavinrufus/agentpassport"
DOCS = "https://docs.agentpassport.fyi"

PYTHON_PACKAGES = (
    "packages/agentpassport",
    "packages/agentpassport-registry",
    "packages/agentpassport-adapters",
    "packages/agentpassport-cli",
)


def _project(rel: str) -> dict:
    path = ROOT / rel / "pyproject.toml"
    with path.open("rb") as handle:
        return tomllib.load(handle)["project"]


def test_python_packages_have_pypi_metadata():
    for rel in PYTHON_PACKAGES:
        project = _project(rel)
        assert project["readme"] == "README.md"
        assert (ROOT / rel / "README.md").is_file()
        assert project["license"] == "Apache-2.0"
        assert "LICENSE" in project["license-files"]
        assert (ROOT / rel / "LICENSE").is_file()
        assert project["keywords"]
        classifiers = project["classifiers"]
        assert "License :: OSI Approved :: Apache Software License" in classifiers
        assert "Programming Language :: Python :: 3" in classifiers
        urls = project["urls"]
        assert urls["Homepage"] == HOMEPAGE
        assert urls["Documentation"] == DOCS
        assert urls["Repository"] == REPOSITORY
        assert project["description"]


def test_npm_package_has_registry_metadata():
    package = json.loads((ROOT / "packages/agentpassport-ts/package.json").read_text())
    assert package["description"]
    assert package["license"] == "Apache-2.0"
    assert package["keywords"]
    assert package["homepage"] == HOMEPAGE
    assert package["repository"]["url"] == "https://github.com/ceavinrufus/agentpassport.git"
    assert package["repository"]["directory"] == "packages/agentpassport-ts"
    assert package["bugs"]["url"] == f"{REPOSITORY}/issues"
    assert (ROOT / "packages/agentpassport-ts/LICENSE").is_file()

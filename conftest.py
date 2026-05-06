"""Root conftest — adds project root to sys.path so `demo` is importable."""

import sys
from pathlib import Path


def pytest_configure(config):  # noqa: ANN001, ANN201
    root = str(Path(__file__).parent)
    if root not in sys.path:
        sys.path.insert(0, root)

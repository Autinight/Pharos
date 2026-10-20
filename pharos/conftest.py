"""Shared temporary-directory fixture."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp():
    with tempfile.TemporaryDirectory() as d:
        # macOS /var is a symlink to /private/var; production paths resolve it.
        yield Path(d).resolve()

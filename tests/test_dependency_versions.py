"""Verify locked dependencies are patched against known vulnerabilities.

aiohttp < 3.14.4 is affected by multiple HIGH severity vulnerabilities
(file descriptor exhaustion, missing request/header timeout, unbounded
memory/CPU use). cryptography < 50.0.0 is affected by HIGH severity
vulnerabilities (exponential path-building, PKCS#7 Bleichenbacher oracle).
"""

from __future__ import annotations

import re
from pathlib import Path

MIN_VERSIONS = {
    "aiohttp": "3.14.4",
    "cryptography": "50.0.0",
}


def _parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def _locked_versions(lock_text: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    # Each package block starts with a line `name = "X"` at column 0.
    blocks = re.split(r'\n(?=name = ")', lock_text)
    for block in blocks:
        match = re.search(r'^name = "([^"]+)"\nversion = "([^"]+)"', block)
        if match:
            versions[match.group(1)] = match.group(2)
    return versions


def test_locked_dependencies_are_patched():
    """aiohttp and cryptography must be at or above the patched versions."""
    lock_text = Path("uv.lock").read_text()
    locked = _locked_versions(lock_text)
    for name, min_version in MIN_VERSIONS.items():
        assert name in locked, f"{name} is not present in uv.lock"
        assert _parse_version(locked[name]) >= _parse_version(min_version), (
            f"{name} is locked at {locked[name]}, but >= {min_version} is required"
        )

"""Harness adapter package: version freeze + capability probing contracts.

Nothing here hard-codes a CLI version, model name or provider. The frozen
snapshot recorded at task init is the only accepted baseline for a run; the
live probe re-checks it before any (future) dispatch and a drift blocks.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..contracts import digest_file, read_json

SNAPSHOT_NAME = "harness_versions.json"


class HarnessVersionError(RuntimeError):
    pass


def snapshot_entry(exe_path: str, probe: dict) -> dict:
    """Compose one frozen entry. ``probe`` comes from harness.probe(exe)."""
    if not os.path.isabs(exe_path):
        raise HarnessVersionError("harness executable must be an absolute path")
    entry = dict(probe)
    entry["exe_path"] = str(Path(exe_path).resolve())
    entry["exe_sha256"] = digest_file(Path(entry["exe_path"]))
    return entry


def load_snapshot(root: Path) -> dict:
    path = Path(root) / "snapshots" / SNAPSHOT_NAME
    if not path.is_file():
        raise HarnessVersionError("frozen harness snapshot missing")
    return read_json(path)


def verify_frozen(frozen: dict, live: dict, exe_path: str) -> None:
    """Fail closed unless the live environment matches what was approved.
    The executable digest is re-measured from disk here, not taken from the
    caller-supplied live dict."""
    current = digest_file(Path(exe_path))
    if current != frozen["exe_sha256"]:
        raise HarnessVersionError("harness executable changed since approval")
    if frozen["exe_sha256"] != live.get("exe_sha256", current):
        raise HarnessVersionError("harness executable digest disagrees")
    if frozen["version"] != live["version"]:
        raise HarnessVersionError(
            f"harness version drift {frozen['version']} -> {live['version']}")
    lost = sorted(set(frozen["capabilities"]) - set(live["capabilities"]))
    if lost:
        raise HarnessVersionError(f"harness capabilities removed since approval: {lost}")

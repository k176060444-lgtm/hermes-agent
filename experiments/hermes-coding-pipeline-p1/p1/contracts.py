"""Stable contracts and immutable input snapshots for P1."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

ROLE_NAMES = (
    "planner", "worker", "spec_reviewer", "quality_reviewer", "tester_gate_a",
    "blind_a", "blind_b", "blind_c", "worker_remediation", "tester_gate_b",
    "arbitrator", "pro_audit",
)
LOCAL_ROLES = tuple(x for x in ROLE_NAMES if not x.startswith("blind_"))
READ_ONLY_ROLES = {"planner", "spec_reviewer", "quality_reviewer", "arbitrator", "pro_audit"}
TEST_ONLY_ROLES = {"tester_gate_a", "tester_gate_b"}
ALLOWED_STATUSES = {"PASS", "FAIL", "APPROVE", "APPROVE_WITH_COMMENTS", "REQUEST_CHANGES", "NEEDS_SPECIALIST", "QUESTION", "REJECT"}
PASS_REVIEW = {"APPROVE", "APPROVE_WITH_COMMENTS"}

class ContractError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return sha256(path.read_bytes())


def canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise ContractError(f"expected JSON object: {path}")
    return obj


def atomic_write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = data.encode("utf-8") if isinstance(data, str) else data
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    with tmp.open("wb") as stream:
        stream.write(blob)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def validate_matrix(matrix: dict[str, Any]) -> None:
    if matrix.get("schema_version") != 1:
        raise ContractError("matrix schema_version must be 1")
    roles = matrix.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(ROLE_NAMES):
        raise ContractError(f"matrix must contain exactly 12 roles: {ROLE_NAMES}")
    nodes = matrix.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        raise ContractError("matrix nodes must be configured")
    for name, role in roles.items():
        if not isinstance(role, dict):
            raise ContractError(f"role {name} must be object")
        for key in ("node", "harness", "primary_model", "backup_model", "permission"):
            if key not in role:
                raise ContractError(f"role {name}: missing {key}")
        if role["node"] not in nodes:
            raise ContractError(f"role {name}: unregistered node")
        if name in LOCAL_ROLES and (not role["harness"] or not role["primary_model"]):
            raise ContractError(f"role {name}: approved harness and primary_model required")
        if name in READ_ONLY_ROLES and role["permission"] != "read_only":
            raise ContractError(f"role {name}: permission must be read_only")
        if name in TEST_ONLY_ROLES and role["permission"] != "test_files_only":
            raise ContractError(f"role {name}: permission must be test_files_only")
        if name.startswith("blind_") and role["harness"] != "external_a2a":
            raise ContractError(f"role {name}: must use external_a2a")
    blind = matrix.get("blind_review", {})
    if blind.get("minimum_distinct_physical_nodes") != 2 or blind.get("third_seat_grace_seconds") != 600:
        raise ContractError("blind review quorum=2 and third-seat grace=600 required")
    if set(blind.get("candidates", [])) != {roles[k]["node"] for k in ("blind_a", "blind_b", "blind_c")}:
        raise ContractError("A2A candidates must match approved blind role nodes")
    if len(blind["candidates"]) != 3:
        raise ContractError("three distinct blind candidates required")


def validate_approval(approval: dict[str, Any], intent_sha: str, matrix_sha: str) -> None:
    if approval.get("gate") != "0.1" or approval.get("approved") is not True:
        raise ContractError("Gate 0.1 approval missing")
    if not approval.get("approval_id") or not approval.get("approved_by") or not approval.get("approved_at"):
        raise ContractError("Gate 0.1 approval lacks provenance")
    if approval.get("intent_sha256") != intent_sha or approval.get("matrix_sha256") != matrix_sha:
        raise ContractError("Gate 0.1 approval input SHA mismatch")


def snapshot_inputs(root: Path, intent: Path, matrix: Path, approval: Path, souls_dir: Path) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    mat = read_json(matrix)
    validate_matrix(mat)
    isha, msha = digest_file(intent), digest_file(matrix)
    validate_approval(read_json(approval), isha, msha)
    snaps = root / "snapshots"
    if snaps.exists():
        raise ContractError("input snapshot already exists")
    snaps.mkdir(parents=True)
    for src, name in ((intent, "intent.md"), (matrix, "matrix.json"), (approval, "gate01.json")):
        shutil.copyfile(src, snaps / name)
    soul_copy = snaps / "souls"
    soul_copy.mkdir()
    hashes = {}
    for role in ROLE_NAMES:
        source = souls_dir / f"{role}.md"
        if not source.is_file():
            raise ContractError(f"missing Soul: {source}")
        shutil.copyfile(source, soul_copy / source.name)
        hashes[role] = digest_file(soul_copy / source.name)
    atomic_write(snaps / "soul_hashes.json", canonical(hashes) + "\n")
    return {"intent_sha256": isha, "matrix_sha256": msha, "approval_sha256": digest_file(snaps / "gate01.json"), "souls_sha256": digest_file(snaps / "soul_hashes.json")}


def safe_task_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,75}", value):
        raise ContractError("task id must be 3-76 safe ASCII characters")
    return value

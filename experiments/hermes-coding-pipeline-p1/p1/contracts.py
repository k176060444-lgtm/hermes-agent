"""Stable contracts and immutable input snapshots for P1."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
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
    primary_nodes = [name for name, spec in nodes.items()
                     if isinstance(spec, dict) and spec.get("platform") == "windows"]
    if len(primary_nodes) != 1:
        raise ContractError("matrix must identify exactly one Windows primary node")
    primary_node = primary_nodes[0]
    for name, role in roles.items():
        if not isinstance(role, dict):
            raise ContractError(f"role {name} must be object")
        for key in ("node", "harness", "primary_model", "backup_model", "permission"):
            if key not in role:
                raise ContractError(f"role {name}: missing {key}")
        if role["node"] not in nodes:
            raise ContractError(f"role {name}: unregistered node")
        if name in LOCAL_ROLES and role["node"] != primary_node:
            raise ContractError(f"role {name} must use configured Windows primary node {primary_node}")
        if name.startswith("blind_") and nodes[role["node"]].get("platform") != "debian":
            raise ContractError(f"role {name} must be on approved Debian blind-review node")
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
    if len(blind["candidates"]) != 3 or len(set(blind["candidates"])) != 3:
        raise ContractError("three distinct blind candidates required")
    if len({roles[k]["node"] for k in ("blind_a", "blind_b", "blind_c")}) != 3:
        raise ContractError("blind roles must use three distinct nodes")


def validate_approval(approval: dict[str, Any], intent_sha: str, matrix_sha: str) -> None:
    if approval.get("gate") != "0.1" or approval.get("approved") is not True:
        raise ContractError("Gate 0.1 approval missing")
    if not approval.get("approval_id") or not approval.get("approved_by") or not approval.get("approved_at"):
        raise ContractError("Gate 0.1 approval lacks provenance")
    if approval.get("intent_sha256") != intent_sha or approval.get("matrix_sha256") != matrix_sha:
        raise ContractError("Gate 0.1 approval input SHA mismatch")


def snapshot_inputs(root: Path, intent: Path, matrix: Path, approval: Path, souls_dir: Path) -> dict[str, str]:
    """Validate exact bytes once and atomically publish fully built snapshots.

    No check-then-copy race: bytes validated and bytes frozen are identical.
    """
    if (root / "snapshots").exists():
        raise ContractError("input snapshot already exists")
    try:
        intent_bytes = intent.read_bytes()
        matrix_bytes = matrix.read_bytes()
        approval_bytes = approval.read_bytes()
        mat = json.loads(matrix_bytes)
        approve = json.loads(approval_bytes)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise ContractError(f"invalid input document: {exc}") from exc
    if not isinstance(mat, dict) or not isinstance(approve, dict):
        raise ContractError("matrix and approval must be JSON objects")
    validate_matrix(mat)
    isha, msha = sha256(intent_bytes), sha256(matrix_bytes)
    validate_approval(approve, isha, msha)
    soul_bytes: dict[str, bytes] = {}
    for role in ROLE_NAMES:
        source = souls_dir / f"{role}.md"
        try:
            raw = source.read_bytes()
            content = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ContractError(f"missing Soul or invalid UTF-8: {source}") from exc
        required = (f"# {role}", "## 身份与职责", "## 输入契约", "## 法定交付物", "## 禁令")
        if len(content.strip()) < 160 or any(item not in content for item in required):
            raise ContractError(f"invalid or empty Soul contract: {role}")
        soul_bytes[role] = raw
    hashes = {role: sha256(raw) for role, raw in soul_bytes.items()}
    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".pending-snapshots-", dir=root))
    try:
        (tmp / "souls").mkdir()
        for name, raw in (("intent.md", intent_bytes), ("matrix.json", matrix_bytes),
                          ("gate01.json", approval_bytes)):
            (tmp / name).write_bytes(raw)
        for role, raw in soul_bytes.items():
            (tmp / "souls" / f"{role}.md").write_bytes(raw)
        (tmp / "soul_hashes.json").write_text(canonical(hashes) + "\n", encoding="utf-8")
        os.replace(tmp, root / "snapshots")
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return {"intent_sha256": isha, "matrix_sha256": msha,
            "approval_sha256": sha256(approval_bytes),
            "souls_sha256": digest_file(root / "snapshots" / "soul_hashes.json")}


def safe_task_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,75}", value):
        raise ContractError("task id must be 3-76 safe ASCII characters")
    return value

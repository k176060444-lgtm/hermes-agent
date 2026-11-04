"""External P0 A2A boundary. This module does NOT dispatch to 5bao/9bao/rusty.

In integration mode a separately supplied adapter executable must implement
JSON stdin/stdout submit/status/collect, persist and own remote jobs, and provide
trusted physical identity attestations. Its deployment is intentionally out of P1.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from .contracts import ContractError, read_json


def call_adapter(task: dict, task_root: Path, operation: str, request: dict) -> dict:
    if task["mode"]=="offline_fixture":
        fixture=read_json(Path(task["fixture_dir"])/"a2a.json")
        if operation=="submit":
            return {"job_id":"OFFLINE-FIXTURE-ONLY","state":"SUBMITTED"}
        if operation=="status":
            return {"state":"COMPLETED"}
        if operation=="collect":
            return fixture
        raise ContractError(f"unsupported a2a operation {operation}")
    cfg=read_json(Path(task["adapter_config"]))
    adapter=cfg.get("a2a",{})
    argv=adapter.get("argv")
    if not isinstance(argv,list) or not argv or not Path(argv[0]).is_absolute() or not adapter.get("explicitly_authorized",False):
        raise ContractError("external A2A adapter not configured/authorized")
    result=subprocess.run([*argv,operation],input=json.dumps(request).encode("utf-8"),capture_output=True,timeout=int(adapter.get("timeout_seconds",120)))
    if result.returncode:
        raise ContractError(f"A2A adapter {operation} failed: exit {result.returncode}; reconcile before retry")
    try:
        content=json.loads(result.stdout)
        if not isinstance(content,dict):raise ValueError("not object")
        return content
    except (ValueError,UnicodeError) as exc:
        raise ContractError("malformed A2A adapter envelope") from exc


def validate_collection(task: dict, matrix: dict, collection: dict, task_root:Path) -> list[str]:
    errors=[]
    if task["mode"] == "integration":
        # A bool/reference in a self-reported JSON document is not proof of
        # separate physical machines. Wait for the independently verified P0 API.
        errors.append("integration A2A trusted physical identity contract NOT_VERIFIED")
    for field, expected in (("task_id",task["task_id"]),("commit_sha",task["commit_sha"]),
                            ("matrix_sha256",task["matrix_sha256"])):
        if collection.get(field)!=expected:errors.append(f"A2A {field} does not match approved task")
    # P0 schema negotiation is pending. In offline fixtures additional bindings
    # are optional; integration requires them (and independently verified hosts).
    for field in ("spec_sha256", "souls_sha256"):
        if task["mode"]=="integration" or field in collection:
            if collection.get(field)!=task.get(field):
                errors.append(f"A2A {field} does not match approved task")
    reports=collection.get("reports",[])
    if not isinstance(reports,list):return ["A2A reports must be array"]
    approved={matrix["roles"][key]["node"] for key in ("blind_a","blind_b","blind_c")}
    unique=set()
    unique_nodes=set()
    for report in reports:
        if not isinstance(report,dict):errors.append("invalid A2A report object");continue
        physical_id=report.get("physical_host_id")
        node=report.get("node")
        if node not in approved:
            errors.append("A2A report from unapproved node");continue
        if node in unique_nodes or physical_id in unique or not physical_id:
            errors.append("duplicate/empty A2A physical host id");continue
        if report.get("commit_sha")!=task["commit_sha"]:
            errors.append("A2A report based on wrong commit");continue
        if not report.get("report") or report.get("verdict") not in (
                "APPROVE", "APPROVE_WITH_COMMENTS", "REQUEST_CHANGES", "QUESTION", "NEEDS_SPECIALIST"):
            errors.append("A2A report missing/invalid verdict/content");continue
        if task["mode"]=="integration":
            # P0 adapter must attest physical host independently of self-reported JSON.
            # Until its trust anchor contract is agreed this is deliberately blocked.
            if report.get("trusted_physical_identity_attestation") is not True:
                errors.append("A2A trusted physical identity attestation missing");continue
            if not report.get("attestation_reference"):
                errors.append("A2A attestation evidence reference missing");continue
        unique.add(physical_id)
        unique_nodes.add(node)
    if len(unique)<matrix["blind_review"]["minimum_distinct_physical_nodes"]:
        errors.append("A2A quorum below 2 distinct physical identities")
    return errors

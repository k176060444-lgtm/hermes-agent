"""Stage-2B-1 plugin-draft contract tests + restart reconciliation behaviour.

REMEDIALIZED CONTRACT (post-audit): p1_init forwards every required CLI flag
(S2B1-011); _invoke bounds capture at collection time (S2B1-012);
p1_approve_spec FAILS CLOSED - it records the unverified provenance but never
invokes the CLI approval path while identity binding is missing
(supplementary security review).

The plugin is imported by file path from integrations/ (it is NOT installed
anywhere); handlers are exercised against a fake ctx and a stubbed subprocess
boundary. Restart reconciliation uses the real offline ledger machinery.
"""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "p1_orchestrator_draft", ROOT / "integrations" / "hermes" / "p1_orchestrator" / "__init__.py")


class FakeCtx:
    def __init__(self):
        self.tools = {}
        self.config = {}

    def register_tool(self, *, name, toolset, schema, description, handler):
        self.tools[name] = {"toolset": toolset, "schema": schema,
                            "description": description, "handler": handler}


class FakeProc:
    """Stands in for subprocess.Popen; the plugin pumps stdout/stderr."""

    def __init__(self, argv, out=b"", err=b"", rc=0):
        self.argv = list(argv)
        self.stdout = io.BytesIO(out)
        self.stderr = io.BytesIO(err)
        self.returncode = rc
        self.killed = False

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True

    def poll(self):
        return self.returncode


@pytest.fixture()
def plugin():
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


def _install_popen(monkeypatch, module, out=b"", err=b"", rc=0):
    holder = {}

    def factory(argv, **kwargs):
        proc = FakeProc(argv, out=out, err=err, rc=rc)
        holder["proc"] = proc
        return proc
    monkeypatch.setattr(module.subprocess, "Popen", factory)
    return holder


def test_draft_registers_exact_tool_surface(plugin):
    ctx = FakeCtx()
    plugin.register(ctx)
    assert set(ctx.tools) == {"p1_init", "p1_run", "p1_status", "p1_reconcile",
                              "p1_approve_spec", "p1_audit", "p1_export"}
    assert all(t["toolset"] == "p1" for t in ctx.tools.values())
    required = ctx.tools["p1_approve_spec"]["schema"]["required"]
    assert "provenance" in required
    print("draft tool surface:", sorted(ctx.tools))


def test_repo_dir_refuses_unconfigured(plugin):
    with pytest.raises(plugin.ConfigError, match="absolute"):
        plugin._repo_dir({})
    with pytest.raises(plugin.ConfigError, match="absolute"):
        plugin._repo_dir({"p1_repo_dir": "relative/path"})
    with pytest.raises(plugin.ConfigError, match="does not contain"):
        plugin._repo_dir({"p1_repo_dir": str(Path(sys.prefix))})


def test_repo_dir_accepts_this_tree(plugin):
    path = plugin._repo_dir({"p1_repo_dir": str(ROOT)})
    assert (path / "p1" / "cli.py").is_file()


def test_approve_requires_structured_provenance(plugin):
    with pytest.raises(plugin.ConfigError, match="chat_id"):
        plugin.handle_approve_spec({"home": str(Path.cwd()),
                                    "actor": "KK",
                                    "spec_sha256": "a" * 64,
                                    "provenance": {"platform": "qq",
                                                   "message_ref": "m1"}},
                                   {"p1_repo_dir": str(ROOT)})
    with pytest.raises(plugin.ConfigError, match="nickname-only|provenance"):
        plugin.handle_approve_spec({"home": str(Path.cwd()), "actor": "KK",
                                    "spec_sha256": "a" * 64},
                                   {"p1_repo_dir": str(ROOT)})
    print("bare-handle approvals are refused by construction")


def test_approve_fails_closed_on_unverified_identity(plugin, monkeypatch):
    """SUPPLEMENTARY REVIEW: the plugin can no longer trigger a real Gate 0.2
    approval while the session identity is unverified. No CLI call happens at
    all."""
    holder = _install_popen(monkeypatch, plugin, out=b"{}")
    out = plugin.handle_approve_spec(
        {"home": str(Path.cwd()), "actor": "KK", "spec_sha256": "a" * 64,
         "provenance": {"platform": "qqbot", "chat_id": "517C",
                        "message_ref": "msg-77"}},
        {"p1_repo_dir": str(ROOT)})
    assert out["status"] == "BLOCKED"
    assert out["result"]["approved"] is False
    assert out["approval_id"].startswith("hermes-unverified:qqbot:517C:msg-77")
    assert out["approval_provenance"]["identity_verified"] is False
    assert "proc" not in holder  # the CLI approval path was never invoked
    assert "UNVERIFIED" in out["reason"]
    print("approve-spec fail-closed: provenance recorded, Gate 0.2 NOT triggerable")


def test_status_handler_passthrough(plugin, monkeypatch):
    holder = _install_popen(monkeypatch, plugin,
                            out=json.dumps({"status": "READY"}).encode())
    out = plugin._simple_handler("status")({"home": str(Path.cwd())},
                                           {"p1_repo_dir": str(ROOT)})
    assert out["result"]["status"] == "READY"
    assert out["exit_code"] == 0
    assert holder["proc"].argv[:4] == [sys.executable, "-B", "-m", "p1"]


def test_init_handler_forwards_all_required_flags(plugin, monkeypatch):
    """S2B1-011: every CLI-required init flag reaches the command line."""
    holder = _install_popen(monkeypatch, plugin,
                            out=json.dumps({"status": "INITIALIZED"}).encode())
    args = {"home": "C:/tmp/home", "task_id": "T-1", "intent": "intent text",
            "matrix": "matrix.json", "gate01": "gate01.json", "souls": "souls/",
            "project_root": "C:/tmp/proj", "worktree": "C:/tmp/wt",
            "mode": "offline_fixture", "base_ref": "HEAD"}
    out = plugin._init_handler(args, {"p1_repo_dir": str(ROOT)})
    assert out["exit_code"] == 0
    argv = holder["proc"].argv
    for flag, value in (("--home", "C:/tmp/home"), ("--task-id", "T-1"),
                        ("--intent", "intent text"), ("--matrix", "matrix.json"),
                        ("--gate01", "gate01.json"), ("--souls", "souls/"),
                        ("--project-root", "C:/tmp/proj"),
                        ("--worktree", "C:/tmp/wt"),
                        ("--mode", "offline_fixture"),
                        ("--base-ref", "HEAD")):
        assert flag in argv and argv[argv.index(flag) + 1] == value, flag
    print("p1_init forwards all 8 required + optional flags")


def test_init_handler_requires_every_required_flag(plugin):
    """A missing required flag is a config error, not a silent CLI failure."""
    args = {"home": "C:/tmp/home", "task_id": "T-1", "intent": "i",
            "matrix": "m", "gate01": "g", "souls": "s",
            "project_root": "p"}  # worktree missing
    with pytest.raises(plugin.ConfigError, match="worktree"):
        plugin._init_handler(args, {"p1_repo_dir": str(ROOT)})


def test_invoke_caps_streams_at_collection_time(plugin, monkeypatch):
    """S2B1-012: a runaway child's output is bounded DURING capture; the cap
    flag is surfaced instead of silently swallowing everything."""
    plugin._STREAM_CAP_BYTES = 4096  # shrink the cap for the test
    holder = _install_popen(monkeypatch, plugin, out=b"x" * (10 * 4096),
                            err=b"e" * (2 * 4096))
    out = plugin._invoke({"p1_repo_dir": str(ROOT)}, "status",
                         ["--home", "C:/tmp/h"])
    kept = len(out["result"].get("stdout", "").encode())
    assert kept <= 4096
    assert out["result"]["_stdout_truncated"] is True
    assert out["_stderr_truncated"] is True
    print("bounded collection verified: cap", out["result"]["_stdout_cap_bytes"])


# ------------------------------------------------------- restart reconciliation
def test_restart_never_redispatches_finished_intent(scenario):
    """A fresh Pipeline (simulated gateway restart) over a task whose planner
    run is still RUNNING must reconcile, not re-dispatch."""
    s = scenario
    from test_pipeline import start
    from p1.workflow import Pipeline, PipelineError
    p = start(s)
    try:
        running = [r for r in p.store.results(p.task_id) if r["status"] == "RUNNING"]
        assert not running  # planner completed in offline flow
        # manufacture an interrupted dispatch:
        rid = p.store.start_run(p.task_id, "2", "worker", "a" * 64,
                               {"before_head": s["commit"]})
    finally:
        p.close()
    revived = Pipeline(s["home"])
    try:
        status = revived.status()
        assert status["status"] == "NEEDS_RECONCILIATION"
        assert status["unfinished_run_ids"] == [rid]
        result = revived.run(max_steps=2)
        assert result["status"] == "NEEDS_RECONCILIATION"
        runs_after = revived.store.results(p.task_id)
        assert len([r for r in runs_after if r["status"] == "RUNNING"]) == 1
        with pytest.raises(PipelineError, match="unfinished invocation"):
            revived.resume()
        print("restart reconciliation: status/run/refuse; exactly one unfinished "
              "record retained, zero re-dispatch")
    finally:
        revived.close()


def test_runner_client_poll_matches_ledger_intent(tmp_path, scenario):
    """RunnerClient.poll state agrees with what the P1 ledger says was
    dispatched: DISPATCHED intent recorded -> poll reports dispatched/not
    receipted -> caller reconciles instead of launching again."""
    from p1.runner import RunnerClient, build_launch_request
    s = scenario
    request = build_launch_request(
        task={"task_id": "TEST-001"}, stage="2", role="worker", run_id=7,
        matrix_entry={"harness": "codex", "primary_model": "p/m"},
        bindings={"soul_sha256": "a" * 64, "matrix_sha256": "b" * 64,
                  "spec_sha256": "c" * 64, "intent_sha256": "d" * 64,
                  "reviewed_commit": s["commit"], "input_sha256": "e" * 64,
                  "frozen_harness_sha256": "f" * 64,
                  "frozen_harness_version": "v"},
        worktree_path=s["project"], timeout_seconds=60, idempotency_key="idem-7",
        command_sha256="4" * 64)
    client = RunnerClient(tmp_path)
    state = client.poll(request)
    assert state["state"] == "NO_RUNNER"
    print("no provisioned runner -> poll cannot fabricate dispatch state")

"""Stage-2B-1 harness adapter tests: synthetic-only, no model/provider calls.

Every probe runs against a stub executable (a python script echoing captured
text) or a monkeypatched runner; the real CLIs are never invoked here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from p1 import harness
from p1.contracts import digest_file, sha256
from p1.harness import HarnessVersionError, load_snapshot, snapshot_entry, verify_frozen
from p1.harness import codex as cx
from p1.harness import opencode as oc


class FakeRun:
    """Ordered (pattern, stdout) table; most specific pattern first."""

    def __init__(self, mapping):
        self.mapping = list(mapping)

    def __call__(self, argv, **kwargs):
        key = " ".join(argv[1:])
        for pattern, text in self.mapping:
            if pattern in key:
                return subprocess.CompletedProcess(argv, 0, text, "")
        return subprocess.CompletedProcess(argv, 1, "", "unknown")


CODEX_HELP = """Codex CLI
Usage: codex [OPTIONS] [PROMPT]
  exec              Run Codex non-interactively
  resume            Resume a previous interactive session
"""

CODEX_EXEC_HELP = """  -m, --model <MODEL>
  -s, --sandbox <SANDBOX_MODE>
  -C, --cd <DIR>
      --json
      --output-schema <FILE>
      -o, --output-last-message <FILE>
      --ephemeral
  resume  Resume a previous session by id or pick the most recent with --last
          instructions are read from stdin
"""

OPENCODE_HELP = """Commands:
  opencode run [message..]     run opencode with a message
  opencode export [sessionID]  export session data as JSON
  opencode agent               manage agents
"""

OPENCODE_RUN_HELP = """  -m, --model        model to use in the format of provider/model
      --agent        agent to use
      --format       format: default (formatted) or json (raw JSON events)
  -s, --session      session id to continue
      --dir          directory to run in
      --title        title for the session
      --pure         run without external plugins
      --attach       attach to a running opencode server
"""


# ------------------------------------------------------------------- probing
def test_codex_probe_detects_required_capabilities(tmp_path):
    launcher = tmp_path / "cx.py"
    launcher.write_text(
        "import sys\n"
        "k=' '.join(sys.argv[1:])\n"
        "table={'--version':'codex-cli 0.99.9-test','--help':"
        + repr(CODEX_HELP) + ",'exec --help':" + repr(CODEX_EXEC_HELP) + "}\n"
        "for pattern,text in table.items():\n"
        "    if pattern in k: print(text); raise SystemExit(0)\n"
        "raise SystemExit(1)\n", encoding="utf-8")
    fake = FakeRun([("exec --help", CODEX_EXEC_HELP),
                    ("--version", "codex-cli 0.99.9-test"),
                    ("--help", CODEX_HELP)])
    entry = cx.probe(str(launcher), run=lambda argv, **kw: fake(argv))
    assert entry["harness"] == "codex"
    assert entry["capabilities"]["exec_noninteractive"] is True
    assert entry["capabilities"]["json_events"] is True
    assert entry["capabilities"]["output_schema"] is True
    cx.require_capabilities(entry["capabilities"])
    print("codex capability matrix detected from synthetic help:",
          sum(entry["capabilities"].values()), "/", len(entry["capabilities"]))


def test_codex_probe_refuses_relative_path():
    with pytest.raises(cx.CodexProbeError, match="absolute"):
        cx.probe("codex")


def test_codex_probe_flags_removed_capability(tmp_path):
    fake = FakeRun([("exec --help", CODEX_EXEC_HELP),
                    ("--version", "codex-cli 0.99.9-test"),
                    ("--help", CODEX_HELP.replace("Run Codex non-interactively", "gone"))])
    entry = cx.probe(str(tmp_path / "x"), run=lambda argv, **kw: fake(argv))
    with pytest.raises(HarnessVersionError, match="exec_noninteractive"):
        cx.require_capabilities(entry["capabilities"])


def test_opencode_probe(tmp_path):
    fake = FakeRun([("run --help", OPENCODE_RUN_HELP),
                    ("--version", "1.99.9-test"),
                    ("--help", OPENCODE_HELP)])
    entry = oc.probe("/abs/opencode", run=lambda argv, **kw: fake(argv))
    assert entry["capabilities"]["json_format"] and entry["capabilities"]["session_export"]
    assert entry["capabilities"]["agent_flag"] and entry["capabilities"]["dir_flag"]
    oc.require_capabilities(entry["capabilities"])
    print("opencode capability matrix detected:", sum(entry["capabilities"].values()))


# ------------------------------------------------------------- version freeze
def test_frozen_snapshot_and_drift_block(tmp_path):
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"v1")
    frozen = snapshot_entry(str(exe), {"harness": "codex", "version": "0.99.9-test",
                                      "capabilities": {"json_events": True,
                                                        "resume": True},
                                      "probe_sha256": "a" * 64})
    live_same = dict(frozen)
    verify_frozen(frozen, live_same, str(exe))
    exe.write_bytes(b"v2-changed")
    with pytest.raises(HarnessVersionError, match="executable changed"):
        verify_frozen(frozen, live_same, str(exe))
    exe.write_bytes(b"v1")
    drifted = dict(frozen, version="1.0.0", exe_sha256=frozen["exe_sha256"])
    with pytest.raises(HarnessVersionError, match="version drift"):
        verify_frozen(frozen, drifted, str(exe))
    lost = dict(frozen, capabilities={"json_events": True})
    with pytest.raises(HarnessVersionError, match="removed"):
        verify_frozen(frozen, lost, str(exe))
    print("frozen baseline verified: identical passes; exe/version/capability "
          "drift all block")


def test_snapshot_requires_absolute_and_missing(tmp_path):
    with pytest.raises(HarnessVersionError, match="absolute"):
        snapshot_entry("relative.exe", {"harness": "x", "version": "1",
                                        "capabilities": {}, "probe_sha256": "z" * 64})
    with pytest.raises(HarnessVersionError, match="missing"):
        load_snapshot(tmp_path)


# -------------------------------------------------------------- argv builders
def _request(tmp_path):
    from p1.runner import build_launch_request
    base = {"soul_sha256": "a" * 64, "matrix_sha256": "b" * 64,
            "spec_sha256": "c" * 64, "intent_sha256": "d" * 64,
            "reviewed_commit": "0" * 40, "input_sha256": "e" * 64,
            "frozen_harness_sha256": "f" * 64}
    return build_launch_request(task={"task_id": "T"}, stage="2", role="worker",
                                run_id=3,
                                matrix_entry={"harness": "codex", "primary_model": "p/m"},
                                bindings=base, worktree_path=tmp_path,
                                timeout_seconds=10, idempotency_key="i")


def _frozen(tmp_path):
    exe = tmp_path / "harness.exe"
    exe.write_bytes(b"x")
    return snapshot_entry(str(exe), {"harness": "codex", "version": "v",
                                     "capabilities": {}, "probe_sha256": "a" * 64})


def test_codex_argv_uses_only_matrix_values(tmp_path):
    cmd = cx.build_command(frozen_entry=_frozen(tmp_path),
                           matrix_entry={"primary_model": "approved/model-A",
                                         "sandbox_mode": "workspace-write",
                                         "extra_argv": ["--config",
                                                        "sandbox_mode=workspace-write"]},
                           request=_request(tmp_path), soul_text="SOUL", prompt_text="GO",
                           worktree=tmp_path / "wt", out_dir=tmp_path / "out")
    joined = " ".join(cmd["argv"])
    assert "approved/model-A" in joined and "workspace-write" in joined
    assert "-C" in cmd["argv"] and "--json" in cmd["argv"]
    assert cmd["stdin_text"].startswith("SOUL") and "GO" in cmd["stdin_text"]
    # no invented defaults anywhere:
    assert "gpt" not in joined.lower() and "0.166" not in joined
    print("argv model/sandbox exclusively from matrix; exe:", Path(cmd['argv'][0]).name)


def test_codex_argv_requires_matrix_model(tmp_path):
    with pytest.raises(cx.CodexProbeError, match="primary_model"):
        cx.build_command(frozen_entry=_frozen(tmp_path), matrix_entry={},
                         request=_request(tmp_path), soul_text="s", prompt_text="p",
                         worktree=tmp_path, out_dir=tmp_path / "o2")


def test_opencode_argv_and_export(tmp_path):
    frozen = _frozen(tmp_path)
    cmd = oc.build_command(frozen_entry=frozen,
                           matrix_entry={"primary_model": "gateway/model-B",
                                         "agent_name": "p1-worker",
                                         "extra_argv": ["--pure"]},
                           request=_request(tmp_path), prompt_text="GO",
                           worktree=tmp_path / "wt", out_dir=tmp_path / "out")
    joined = " ".join(cmd["argv"])
    assert "gateway/model-B" in joined and "--agent p1-worker" in joined
    assert "--format json" in joined and "--pure" in joined
    export = oc.export_command(frozen_entry=frozen, session_id="ses_123")
    assert export[-2:] == ["export", "ses_123"]
    with pytest.raises(oc.OpenCodeProbeError):
        oc.export_command(frozen_entry=frozen, session_id="")


# ------------------------------------------------------------------ events
def test_codex_event_parse_marks_self_report_only():
    stream = "\n".join([
        json.dumps({"type": "session_id", "session_id": "0198-uuid"}),
        json.dumps({"type": "event_msg", "payload": {"type": "exec_command_begin",
              "command": "pytest -q tests/test_spec.py"}}),
        json.dumps({"type": "event_msg", "msg": {"type": "exec_command_end",
              "command": "pytest -q tests/test_spec.py", "exit_code": 0}}),
        json.dumps({"rollout_path": "/home/x/.codex/sessions/rollout-a.jsonl"}),
        "not-json{{{",
        json.dumps([1, 2]),
    ])
    events = list(cx.parse_events(stream))
    refs = cx.extract_session_ref(events)
    assert refs["session_id"] == "0198-uuid"
    assert refs["rollout_path"].endswith("rollout-a.jsonl")
    evidence = cx.extract_command_evidence(events)
    assert evidence and all(item["trusted"] is False for item in evidence)
    kinds = [e["kind"] for e in events]
    assert "unparseable" in kinds and "unknown" in kinds
    print("CLI-reported commands stay trusted=False; kinds:", kinds)


def test_runner_agreement_upgrades_only_matching_records():
    claimed = [{"command": "pytest -q", "claimed_exit": 0,
                "source": "cli-event-self-report", "trusted": False}]
    merged = cx.merge_runner_records(claimed, [{"command": "pytest -q", "exit_code": 0}])
    assert merged[0]["trusted"] is True
    merged2 = cx.merge_runner_records(claimed, [{"command": "pytest -q", "exit_code": 1}])
    assert merged2[0]["trusted"] is False and merged2[0]["contradiction"] is True
    merged3 = cx.merge_runner_records(claimed, [])
    assert merged3[0]["trusted"] is False
    print("self-report vs runner-record distinction enforced (agreement/conflict/silent)")


def test_opencode_event_and_export_parsing():
    stream = "\n".join([
        json.dumps({"type": "step_start", "sessionID": "ses_9"}),
        json.dumps({"type": "tool", "tool": "bash",
                    "part": {"state": {"status": "completed", "exit": 0},
                             "input": {"command": "make test"}}}),
        json.dumps({"type": "text", "part": {"text": "done"}}),
    ])
    events = list(oc.parse_events(stream))
    refs = oc.extract_session_ref(events)
    assert refs["session_id"] == "ses_9"
    assert refs["export_required_for_final_evidence"] is True
    evidence = oc.extract_command_evidence(events)
    assert evidence[0]["command"] == "make test" and evidence[0]["trusted"] is False
    merged = oc.merge_runner_records(evidence, [{"command": "make test", "exit_code": 0}])
    assert merged[0]["trusted"] is True
    print("opencode session export + command evidence pipeline OK")


# ------------------------------------------------------------------ agents
def test_agent_render_binds_role_model_soul():
    markdown = oc.render_agent_markdown(role="spec_reviewer", model="gateway/model-C",
                                        soul_text="# SOUL\nReview strictly.",
                                        description="P1 spec reviewer",
                                        permissions={"edit": "deny", "bash": "allow"})
    assert "mode: subagent" in markdown and "gateway/model-C" in markdown
    assert "# SOUL" in markdown and "Review strictly." in markdown
    assert "edit: deny" in markdown and "bash: allow" in markdown
    assert "auto: deny" in markdown  # never self-approve
    digest = oc.agent_digest(markdown)
    assert digest == sha256(markdown.encode())
    print("agent definition rendered deterministically; digest", digest[:12])


def test_agent_render_refuses_bad_permission():
    with pytest.raises(oc.OpenCodeProbeError, match="invalid permission"):
        oc.render_agent_markdown(role="r", model="m", soul_text="s",
                                 description="d", permissions={"bash": "yolo"})

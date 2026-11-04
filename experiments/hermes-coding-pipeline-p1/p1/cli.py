"""CLI boundary for Hermes P1; no release/deploy command exists."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .contracts import ContractError
from .workflow import Pipeline,PipelineError,initialize
from .state import StateError


def parser():
    p=argparse.ArgumentParser(prog="p1-pipeline",description="Hermes Coding Pipeline P1: Phase 0.2 -> Gate 5.9")
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("init",help="Snapshot approved inputs and create durable task state")
    for flag in ("home","task-id","intent","matrix","gate01","souls","project-root","worktree"):
        a.add_argument("--"+flag,required=True)
    a.add_argument("--mode",choices=["offline_fixture","integration"],default="offline_fixture")
    a.add_argument("--fixtures")
    a.add_argument("--adapters")
    a.add_argument("--safety-manifest")
    a.add_argument("--base-ref",default="HEAD")
    for name in ("run","status","resume","reconcile","audit","export"):
        s=sub.add_parser(name)
        s.add_argument("--home",required=True)
        if name in ("run","resume"):s.add_argument("--max-steps",type=int,default=40)
    b=sub.add_parser("approve-spec",help="Explicit human Gate 0.2 confirmation")
    b.add_argument("--home",required=True)
    b.add_argument("--actor",required=True)
    b.add_argument("--approval-id",required=True)
    b.add_argument("--spec-sha256",required=True)
    return p


def main(argv=None)->int:
    args=parser().parse_args(argv)
    try:
        if args.command=="init":
            data=initialize(Path(args.home),args.task_id,Path(args.intent),Path(args.matrix),Path(args.gate01),Path(args.souls),Path(args.project_root),Path(args.worktree),args.mode,
                            Path(args.fixtures) if args.fixtures else None,Path(args.adapters) if args.adapters else None,args.base_ref,
                            Path(args.safety_manifest) if args.safety_manifest else None)
            print(json.dumps({"task_id":data["task_id"],"stage":data["stage"],"mode":data["mode"]},ensure_ascii=False))
            return 0
        pipe=Pipeline(Path(args.home))
        try:
            if args.command=="run":result=pipe.run(max_steps=args.max_steps)
            elif args.command=="resume":result=pipe.resume(max_steps=args.max_steps)
            elif args.command=="approve-spec":
                pipe.approve_spec(args.actor,args.approval_id,args.spec_sha256)
                result=pipe.status()
            elif args.command=="status":result=pipe.status()
            elif args.command=="reconcile":result=pipe.reconcile()
            elif args.command=="audit":result={"evidence":pipe.verify_evidence(),"status":pipe.status()}
            elif args.command=="export":
                print(pipe.export_report())
                return 0
            else:raise ValueError("unsupported command")
            print(json.dumps(result,indent=2,ensure_ascii=False))
            return 0
        finally:pipe.close()
    except (ContractError,PipelineError,StateError,OSError,ValueError) as exc:
        print(json.dumps({"error":str(exc)},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=="__main__":raise SystemExit(main())

"""Git snapshots and isolated worktrees. No network, push or production deploy."""
from __future__ import annotations
import hashlib
import os
import subprocess
from pathlib import Path
from .contracts import ContractError, canonical, sha256


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git","-C",str(repo),*args],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=60)
    if result.returncode:
        raise ContractError(f"git {' '.join(args)} failed: {result.stderr.strip()[:1000]}")
    return result.stdout.strip()


def head(repo: Path) -> str:
    return git(repo,"rev-parse","HEAD")


def clean(repo: Path) -> bool:
    return not git(repo,"status","--porcelain","--untracked-files=normal")


def index_digest(repo: Path) -> str:
    """Git index SHA (staged blobs, paths, file modes, index stages)."""
    result=subprocess.run(["git","-C",str(repo),"ls-files","--stage","-z"],capture_output=True,timeout=60)
    if result.returncode:
        raise ContractError("cannot inspect Git index")
    return sha256(result.stdout)


def git_status(repo: Path) -> str:
    return git(repo, "status", "--porcelain=v1", "--untracked-files=all")


def test_commit_transition(repo: Path, previous: str, current: str) -> tuple[bool, list[str]]:
    """Accept tester-created commits only when additive descendants and test-only."""
    if previous == current:
        return True, []
    ancestor=subprocess.run(["git","-C",str(repo),"merge-base","--is-ancestor",previous,current],
                            capture_output=True,timeout=60)
    if ancestor.returncode:
        return False, []
    delta=git(repo,"diff","--name-only",previous,current).splitlines()
    return all(test_path(p) for p in delta), delta


def inventory(root: Path) -> dict[str,str]:
    """Hash all Git-visible tracked and non-ignored untracked files including test files.

    Excludes only Git metadata and Git-ignored files. Symlinks are hashed by link
    target text instead of following them outside the workspace.
    """
    result=subprocess.run(["git","-C",str(root),"ls-files","-z","--cached","--others","--exclude-standard"],capture_output=True,timeout=60)
    if result.returncode:
        raise ContractError("unable to enumerate repository files")
    found={}
    for name in result.stdout.split(b"\0"):
        if not name: continue
        rel=os.fsdecode(name)
        file=root/rel
        if file.is_symlink():
            value=b"symlink:"+os.fsencode(os.readlink(file))
        elif file.is_file():
            value=file.read_bytes()
        else:
            value=b"<missing>"
        found[rel.replace("\\","/")] = sha256(value)
    return found


def inventory_hash(lookup: dict[str,str]) -> str:
    return sha256(canonical(lookup).encode("utf-8"))


def changed(before: dict[str,str], after: dict[str,str]) -> set[str]:
    return {key for key in (before.keys()|after.keys()) if before.get(key)!=after.get(key)}


def test_path(path: str) -> bool:
    p=Path(path)
    return bool("tests" in p.parts or p.name.startswith("test_") or p.name.endswith("_test.py") or p.name.endswith(".test.ts") or p.name.endswith(".spec.ts"))


def create_worktree(project_root: Path, target: Path, task_id: str, base_ref: str, offline: bool) -> dict:
    root=project_root.resolve()
    if not (root/".git").exists():
        raise ContractError("project_root is not a Git repository")
    if not clean(root):
        raise ContractError("project_root has uncommitted or untracked changes")
    target=target.resolve()
    if target.exists():
        raise ContractError("worktree path already exists; refusing to reuse")
    if not offline:
        if os.name!="nt" or target.drive.upper()!="E:":
            raise ContractError("integration mode requires native Windows E: worktree path")
    target.parent.mkdir(parents=True,exist_ok=True)
    branch=f"wt/{task_id}"
    git(root,"worktree","add","-b",branch,str(target),base_ref)
    if not clean(target):
        raise ContractError("new worktree is not clean")
    return {"worktree":str(target),"branch":branch,"commit_sha":head(target),"clean":True}

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
    """Require clean status plus checked-out content matching the index.

    `git status` can skip tracked paths marked assume-unchanged or
    skip-worktree. Neither bit is acceptable for a frozen audit baseline.
    """
    return (not git(repo,"status","--porcelain","--untracked-files=normal")
            and not hidden_index_flags(repo)
            and not tracked_worktree_mismatch(repo))


def hidden_index_flags(repo: Path) -> list[str]:
    result=subprocess.run(["git","-C",str(repo),"ls-files","-v","-z"],
                          capture_output=True,timeout=60)
    if result.returncode:
        raise ContractError("unable to inspect Git index flags")
    flags=[]
    for entry in result.stdout.split(b"\0"):
        if entry and entry[:2]!=b"H ":
            flags.append(os.fsdecode(entry[2:]))
    return flags


def tracked_worktree_mismatch(repo: Path) -> list[str]:
    """Compare every tracked worktree blob with the staged Git blob.

    Git's `hash-object --path` applies repository clean filters (including
    CRLF normalization), so legitimate checked-out file representations do
    not yield false positives. Symlink targets are hashed as link contents.
    This intentionally favors correctness over speed in audit-sized repos.
    """
    result=subprocess.run(["git","-C",str(repo),"ls-files","--stage","-z"],
                          capture_output=True,timeout=60)
    if result.returncode:
        raise ContractError("cannot enumerate index blobs")
    mismatches=[]
    for record in result.stdout.split(b"\0"):
        if not record:continue
        meta,raw_path=record.split(b"\t",1)
        mode,blob,stage=meta.split()
        rel=os.fsdecode(raw_path)
        if stage!=b"0":
            mismatches.append(rel);continue
        file=repo/rel
        try:
            if file.is_symlink():
                raw=os.fsencode(os.readlink(file))
            elif file.is_file():
                raw=file.read_bytes()
            else:
                mismatches.append(rel);continue
        except OSError:
            mismatches.append(rel);continue
        checked=subprocess.run(["git","-C",str(repo),"hash-object","--stdin","--path",rel],
                               input=raw,capture_output=True,timeout=60)
        if checked.returncode or checked.stdout.strip()!=blob:
            mismatches.append(rel)
    return mismatches


def index_digest(repo: Path) -> str:
    """Git index SHA (staged blobs, paths, file modes, index stages)."""
    result=subprocess.run(["git","-C",str(repo),"ls-files","--stage","-z"],capture_output=True,timeout=60)
    if result.returncode:
        raise ContractError("cannot inspect Git index")
    flags=subprocess.run(["git","-C",str(repo),"ls-files","-v","-z"],
                         capture_output=True,timeout=60)
    if flags.returncode:
        raise ContractError("cannot inspect Git index flags")
    return sha256(result.stdout+b"\0FLAGS\0"+flags.stdout)


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
    # Git's default core.quotePath serializes non-ASCII names with octal
    # escapes. Parse NUL-separated *bytes* instead: no quotation, tab or
    # newline ambiguity even with Unicode, spaces and special characters.
    result=subprocess.run(["git","-C",str(repo),"diff","--name-status","-z",
                           "--no-renames",previous,current],capture_output=True,timeout=60)
    if result.returncode:
        raise ContractError("unable to inspect Tester commit delta")
    fields=result.stdout.split(b"\0")
    if fields[-1:] == [b""]:
        fields.pop()
    if len(fields)%2:
        raise ContractError("invalid NUL-delimited Git delta")
    changes=[(fields[i].decode("ascii","replace"),os.fsdecode(fields[i+1]))
             for i in range(0,len(fields),2)]
    delta=[f"{status}\t{filename}" for status,filename in changes]
    # No collection controllers, symlinks, gitlinks, rewrites, deletions,
    # renames or non-case files in new Tester commits.
    allowed=all(status=="A" and test_path(name) for status,name in changes)
    if allowed:
        for _status,name in changes:
            tree=subprocess.run(["git","-C",str(repo),"ls-tree","-z",current,"--",name],
                                capture_output=True,timeout=60)
            if tree.returncode or not tree.stdout.endswith(b"\0"):
                allowed=False;break
            entries=tree.stdout[:-1].split(b"\0")
            if len(entries)!=1 or b"\t" not in entries[0]:
                allowed=False;break
            mode_type,actual_name=entries[0].split(b"\t",1)
            tokens=mode_type.split(b" ")
            if (len(tokens)!=3 or tokens[0] not in (b"100644",b"100755") or
                    tokens[1]!=b"blob" or os.fsdecode(actual_name)!=name):
                allowed=False;break
    return allowed, delta


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
    """Only isolated test *case files*, never collection/import configuration.

    A filename under ``tests/`` is not automatically safe: pytest's
    ``conftest.py`` can change collection for the entire suite.  Likewise,
    pytest.ini, __init__.py and helper modules can redirect imports.  Explicit
    test-module naming is required for all newly created Tester files.
    """
    from pathlib import PurePosixPath
    if not isinstance(path, str) or not path or "\\" in path:
        return False
    p=PurePosixPath(path)
    if p.is_absolute() or any(part in ("", ".", "..") for part in p.parts):
        return False
    name=p.name
    if name.startswith(".") or any(part.startswith(".") for part in p.parts):
        return False
    return bool(
        (name.startswith("test_") and name.endswith(".py") and len(name)>8)
        or (name.endswith("_test.py") and len(name)>8)
        or any(name.endswith(suffix) and len(name)>len(suffix)
               for suffix in (".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx",
                              ".test.js", ".spec.js", ".test.jsx", ".spec.jsx",
                              ".test.mjs", ".spec.mjs", "_test.go"))
    )


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

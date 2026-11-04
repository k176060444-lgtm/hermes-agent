"""SQLite-backed single-writer durable workflow state and hash-chained journal."""
from __future__ import annotations
import json
import os
import sqlite3
import time
import hashlib
from pathlib import Path
from contextlib import contextmanager
from .contracts import canonical

class StateError(RuntimeError):
    pass

class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY, data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
            created_at REAL NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
            prev_hash TEXT NOT NULL, event_hash TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
            stage TEXT NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL,
            created_at REAL NOT NULL, finished_at REAL,
            input_sha TEXT NOT NULL, output_sha TEXT, details TEXT NOT NULL
          );
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def create(self, data: dict):
        with self.db:
            self.db.execute("INSERT INTO tasks VALUES (?,?)", (data["task_id"], canonical(data)))
            self._event(data["task_id"], "task_created", {"stage":data["stage"],"mode":data["mode"]})

    def load(self, task_id: str) -> dict:
        row = self.db.execute("SELECT data FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise StateError(f"unknown task: {task_id}")
        return json.loads(row[0])

    def save(self, data: dict, kind: str, payload: dict | None = None):
        with self.db:
            cur = self.db.execute("UPDATE tasks SET data=? WHERE task_id=?", (canonical(data), data["task_id"]))
            if cur.rowcount != 1:
                raise StateError("task disappeared")
            self._event(data["task_id"], kind, payload or {"stage":data["stage"],"status":data["status"]})

    def _event(self, task_id: str, kind: str, payload: dict):
        prev_row = self.db.execute("SELECT event_hash FROM events WHERE task_id=? ORDER BY id DESC LIMIT 1", (task_id,)).fetchone()
        prev = prev_row[0] if prev_row else "0"*64
        timestamp = time.time()
        payload = dict(payload)
        current_task = self.db.execute("SELECT data FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if current_task is None:
            raise StateError("missing task while journaling")
        # Tie the mutable task row to the append-only hash chain. Detect row-only
        # tampering before any subsequent dispatch, not just at final Gate 5.85.
        payload["_task_sha256"] = hashlib.sha256(current_task[0].encode("utf-8")).hexdigest()
        serialized = canonical(payload)
        body = canonical({"task_id":task_id,"created_at":timestamp,"kind":kind,"payload":serialized,"prev_hash":prev})
        current = hashlib.sha256(body.encode()).hexdigest()
        self.db.execute("INSERT INTO events(task_id,created_at,kind,payload,prev_hash,event_hash) VALUES (?,?,?,?,?,?)",(task_id,timestamp,kind,serialized,prev,current))

    def audit_events(self, task_id: str) -> list[str]:
        errors = []
        prev = "0"*64
        rows = self.db.execute("SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
        if not rows:
            errors.append("journal empty")
        for row in rows:
            d = dict(row)
            body = canonical({k:d[k] for k in ("task_id","created_at","kind","payload","prev_hash")})
            actual = hashlib.sha256(body.encode()).hexdigest()
            if d["prev_hash"] != prev or d["event_hash"] != actual:
                errors.append(f"event {d['id']}: hash-chain mismatch")
            prev = d["event_hash"]
        latest = rows[-1] if rows else None
        if latest:
            try:
                expected = json.loads(latest["payload"])["_task_sha256"]
                current = self.db.execute("SELECT data FROM tasks WHERE task_id=?", (task_id,)).fetchone()
                actual = hashlib.sha256(current[0].encode("utf-8")).hexdigest()
                if expected != actual:
                    errors.append("task row does not match the last journal state hash")
            except (KeyError, ValueError, TypeError, IndexError) as exc:
                errors.append(f"task state journal integrity error: {exc}")
        # Two-way binding: every event must still have its run row, and every
        # run row must have its exact recorded dispatch metadata. Rebuilding
        # mutable runs rows or deleting them cannot silently pass verification.
        dispatched={}
        finished={}
        for event in rows:
            if event["kind"] not in ("execution_dispatched", "execution_finished"):
                continue
            try:
                data=json.loads(event["payload"])
                run_id=data["run_id"]
                if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
                    raise ValueError("invalid run_id")
                if event["kind"]=="execution_dispatched":
                    if run_id in dispatched:
                        errors.append(f"run {run_id}: duplicate dispatch event")
                    dispatched[run_id]=data
                else:
                    if run_id in finished:
                        errors.append(f"run {run_id}: duplicate finish event")
                    finished[run_id]=data
            except (ValueError,TypeError,KeyError) as exc:
                errors.append(f"run event malformed {event['id']}: {exc}")
        runs=self.db.execute("SELECT * FROM runs WHERE task_id=?", (task_id,)).fetchall()
        indexed={run["id"]:run for run in runs}
        for run_id in dispatched:
            if run_id not in indexed:
                errors.append(f"run {run_id}: dispatch journal has no run row")
        for run_id in finished:
            if run_id not in indexed:
                errors.append(f"run {run_id}: finish journal has no run row")
            if run_id not in dispatched:
                errors.append(f"run {run_id}: finish journal has no dispatch event")
        for run_id,run in indexed.items():
            if run_id not in dispatched:
                errors.append(f"run {run_id}: dispatch event missing")
                continue
            origin=dispatched[run_id]
            if (origin.get("input_sha") != run["input_sha"] or
                origin.get("stage") != run["stage"] or
                origin.get("role") != run["role"]):
                errors.append(f"run {run_id}: stage/role/input differs from dispatch journal")
            if run["status"]=="COMPLETED":
                record=finished.get(run_id)
                if not record:
                    errors.append(f"run {run_id}: finish event missing")
                else:
                    details_sha=hashlib.sha256(run["details"].encode("utf-8")).hexdigest()
                    if (record.get("details_sha256")!=details_sha or
                        record.get("output_sha")!=run["output_sha"] or
                        record.get("status")!=run["status"]):
                        errors.append(f"run {run_id}: run details or output differs from journal")
            elif run["status"]=="RUNNING":
                if run_id in finished:
                    errors.append(f"run {run_id}: terminal journal for unfinished run")
            else:
                errors.append(f"run {run_id}: unsupported status {run['status']}")
        return errors

    def start_run(self, task_id: str, stage: str, role: str, input_sha: str, details: dict) -> int:
        with self.db:
            cur=self.db.execute("INSERT INTO runs(task_id,stage,role,status,created_at,input_sha,details) VALUES (?,?,?,?,?,?,?)",(task_id,stage,role,"RUNNING",time.time(),input_sha,canonical(details)))
            self._event(task_id,"execution_dispatched",{"stage":stage,"role":role,"run_id":cur.lastrowid,
                     "input_sha":input_sha})
            return int(cur.lastrowid)

    def finish_run(self, task_id: str, run_id: int, status: str, output_sha: str, details: dict):
        with self.db:
            detail_text=canonical(details)
            cur=self.db.execute("UPDATE runs SET status=?, finished_at=?, output_sha=?, details=? WHERE id=? AND task_id=?",(status,time.time(),output_sha,detail_text,run_id,task_id))
            if cur.rowcount!=1:
                raise StateError("missing run to finalize")
            self._event(task_id,"execution_finished",{"run_id":run_id,"status":status,"output_sha":output_sha,
                "details_sha256":hashlib.sha256(detail_text.encode("utf-8")).hexdigest()})

    def running(self, task_id: str) -> list[dict]:
        return [dict(x) for x in self.db.execute("SELECT * FROM runs WHERE task_id=? AND status='RUNNING'",(task_id,)).fetchall()]

    def results(self, task_id: str) -> list[dict]:
        return [dict(x) for x in self.db.execute("SELECT * FROM runs WHERE task_id=? ORDER BY id",(task_id,)).fetchall()]

@contextmanager
def exclusive_lock(path: Path):
    """Windows and POSIX process lock. No stale lease takeover after a crash."""
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:
                raise StateError("task already controlled by another process") from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as exc:
                raise StateError("task already controlled by another process") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)

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
        return errors

    def start_run(self, task_id: str, stage: str, role: str, input_sha: str, details: dict) -> int:
        with self.db:
            cur=self.db.execute("INSERT INTO runs(task_id,stage,role,status,created_at,input_sha,details) VALUES (?,?,?,?,?,?,?)",(task_id,stage,role,"RUNNING",time.time(),input_sha,canonical(details)))
            self._event(task_id,"execution_dispatched",{"stage":stage,"role":role,"run_id":cur.lastrowid})
            return int(cur.lastrowid)

    def finish_run(self, task_id: str, run_id: int, status: str, output_sha: str, details: dict):
        with self.db:
            self.db.execute("UPDATE runs SET status=?, finished_at=?, output_sha=?, details=? WHERE id=? AND task_id=?",(status,time.time(),output_sha,canonical(details),run_id,task_id))
            self._event(task_id,"execution_finished",{"run_id":run_id,"status":status,"output_sha":output_sha})

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

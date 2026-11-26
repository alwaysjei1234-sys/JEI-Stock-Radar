"""Local-only persistent job lease for the public hybrid audit pilot.

Not a distributed lock: use a local disk, never a Drive/FUSE/network share.
The deterministic audit remains available independently of model completion.
"""
from contextlib import closing, contextmanager
import hashlib
import math
import sqlite3
import time
import uuid
from pathlib import Path
from tools.jei_batch_checkpoint import checkpoint_key

MAX_ATTEMPTS = 3
LEASE_SECONDS = 120
RETRY_SECONDS = 60

def job_key(raw, model, engine):
    return checkpoint_key(hashlib.sha256(raw).hexdigest(), "hybrid_public_summary",
                          {"model": model, "engine": engine, "schema": 1})

def valid_text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 4000

class JobStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                key TEXT PRIMARY KEY, status TEXT NOT NULL, token TEXT,
                lease_until REAL NOT NULL, attempts INTEGER NOT NULL,
                result TEXT)""")

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=5)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def _transaction(self):
        with closing(self._connect()) as db:
            with db:
                yield db

    def claim(self, key, *, now=None):
        now = time.time() if now is None else now
        if not math.isfinite(now):
            raise ValueError("invalid clock")
        with self._transaction() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone()
            if row:
                if row["status"] == "complete":
                    if not valid_text(row["result"]):
                        raise ValueError("invalid cached result")
                    return "cached", row["result"]
                if row["lease_until"] > now:
                    return "busy", None
                if row["attempts"] >= MAX_ATTEMPTS:
                    return "exhausted", None
                attempts = row["attempts"] + 1
            else:
                attempts = 1
            token = uuid.uuid4().hex
            db.execute("""INSERT OR REPLACE INTO jobs
                (key,status,token,lease_until,attempts,result)
                VALUES(?, 'running', ?, ?, ?, NULL)""",
                (key, token, now + LEASE_SECONDS, attempts))
            return "claimed", token

    def finish(self, key, token, result, *, now=None):
        now = time.time() if now is None else now
        if not math.isfinite(now) or not valid_text(result):
            raise ValueError("invalid completion")
        with self._transaction() as db:
            cursor = db.execute("""UPDATE jobs SET status='complete',result=?,
                token=NULL,lease_until=0 WHERE key=? AND token=?
                AND status='running' AND lease_until>?""",
                (result.strip(), key, token, now))
            return cursor.rowcount == 1

    def fail(self, key, token, *, now=None):
        now = time.time() if now is None else now
        if not math.isfinite(now):
            raise ValueError("invalid clock")
        with self._transaction() as db:
            cursor = db.execute("""UPDATE jobs SET status='retry',token=NULL,
                lease_until=? WHERE key=? AND token=? AND status='running'
                AND lease_until>?""", (now + RETRY_SECONDS, key, token, now))
            return cursor.rowcount == 1

    def summarize_once(self, key, aggregate, summarize):
        status, value = self.claim(key)
        if status == "cached":
            return value, "cache"
        if status != "claimed":
            raise ValueError("summary_" + status)
        try:
            result = summarize(aggregate)
            if not self.finish(key, value, result):
                raise ValueError("summary_lease_lost")
        except Exception:
            self.fail(key, value)
            raise
        return result.strip(), "model"

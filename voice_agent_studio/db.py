from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import AppConfig
from .security import Vault, hash_password, verify_password

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  csrf_token TEXT NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS secrets (
  name TEXT PRIMARY KEY,
  ciphertext BLOB NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at INTEGER NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  details TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calls (
  id TEXT PRIMARY KEY,
  started_at INTEGER NOT NULL,
  ended_at INTEGER,
  source TEXT NOT NULL,
  intent TEXT NOT NULL DEFAULT '',
  outcome TEXT NOT NULL DEFAULT 'received',
  metadata TEXT NOT NULL DEFAULT '{}'
);
"""


class Database:
    def __init__(self, path: Path, vault: Vault):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        self.vault = vault
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def has_users(self) -> bool:
        with self.connect() as conn:
            return bool(conn.execute("SELECT 1 FROM users LIMIT 1").fetchone())

    def create_user(self, username: str, password: str) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)", (username, hash_password(password), int(time.time())))
            conn.commit()
        self.audit(username, "user.created", {})

    def authenticate(self, username: str, password: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute("SELECT id,password_hash FROM users WHERE username=?", (username,)).fetchone()
        if row and verify_password(password, row["password_hash"]):
            return int(row["id"])
        return None

    def create_session(self, user_id: int, token_hash: str, csrf_token: str, expires_at: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
            conn.execute("INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES(?,?,?,?)", (token_hash, user_id, csrf_token, expires_at))
            conn.commit()

    def session(self, token_hash: str):
        with self.connect() as conn:
            return conn.execute("SELECT s.*,u.username FROM sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires_at>?", (token_hash, int(time.time()))).fetchone()

    def delete_session(self, token_hash: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
            conn.commit()

    def get_config(self) -> AppConfig:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='config'").fetchone()
        return AppConfig.model_validate_json(row["value"]) if row else AppConfig()

    def save_config(self, config: AppConfig, actor: str) -> None:
        now = int(time.time())
        with self.connect() as conn:
            conn.execute("INSERT INTO settings(key,value,updated_at) VALUES('config',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (config.model_dump_json(), now))
            conn.commit()
        self.audit(actor, "config.updated", {"schema_version": config.schema_version})

    def set_secret(self, name: str, value: str, actor: str) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO secrets(name,ciphertext,updated_at) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET ciphertext=excluded.ciphertext,updated_at=excluded.updated_at", (name, self.vault.encrypt(value), int(time.time())))
            conn.commit()
        self.audit(actor, "secret.updated", {"name": name})

    def get_secret(self, name: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT ciphertext FROM secrets WHERE name=?", (name,)).fetchone()
        return self.vault.decrypt(row["ciphertext"]) if row else None

    def secret_status(self) -> dict[str, bool]:
        allowed = ("sip_password", "provider_api_key", "stt_api_key", "tts_api_key")
        with self.connect() as conn:
            names = {r["name"] for r in conn.execute("SELECT name FROM secrets")}
        return {name: name in names for name in allowed}

    def audit(self, actor: str, action: str, details: dict) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO audit_log(created_at,actor,action,details) VALUES(?,?,?,?)", (int(time.time()), actor, action, json.dumps(details, separators=(",", ":"))))
            conn.commit()

    def audits(self, limit: int = 100) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT created_at,actor,action,details FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "details": json.loads(r["details"])} for r in rows]

    def start_call(self, call_id: str, source: str, metadata: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO calls(id,started_at,source,metadata) VALUES(?,?,?,?)",
                (call_id, int(time.time()), source[:128], json.dumps(metadata, separators=(",", ":"))),
            )
            conn.commit()

    def finish_call(self, call_id: str, intent: str, outcome: str, metadata: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE calls SET ended_at=?,intent=?,outcome=?,metadata=? WHERE id=?",
                (
                    int(time.time()),
                    intent[:128],
                    outcome[:128],
                    json.dumps(metadata, separators=(",", ":")),
                    call_id,
                ),
            )
            conn.commit()

    def calls(self, limit: int = 100) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id,started_at,ended_at,source,intent,outcome,metadata "
                "FROM calls ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata"])} for row in rows]

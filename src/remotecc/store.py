from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import fcntl


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SessionRecord:
    session_id: str
    name: str
    local_dir: str
    ssh_target: str
    remote_root: str
    remote_dir: str
    tmux_session: str
    claude_command: str
    model: str | None
    model_profile: str | None
    auth_mode: str
    status: str
    created_at: str
    updated_at: str
    control_path: str | None = None
    last_push_at: str | None = None
    last_pull_at: str | None = None
    last_seen_at: str | None = None

    @classmethod
    def from_dict(cls, payload: dict) -> "SessionRecord":
        normalized = dict(payload)
        normalized.setdefault("model", None)
        normalized.setdefault("model_profile", None)
        normalized.setdefault("auth_mode", "control_master" if normalized.get("control_path") else "key")
        return cls(**normalized)

    def to_dict(self) -> dict:
        return asdict(self)


class SessionStore:
    def __init__(self, registry_path: Path | None = None) -> None:
        env_path = os.environ.get("REMOTECC_REGISTRY")
        self.registry_path = Path(env_path).expanduser() if env_path else (
            registry_path or Path.home() / ".remotecc" / "sessions.json"
        )
        self.registry_path = self.registry_path.expanduser()
        self.lock_path = self.registry_path.with_suffix(self.registry_path.suffix + ".lock")

    @contextmanager
    def _transaction(self) -> Iterator[dict]:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            data = self._read_unlocked()
            try:
                yield data
            except Exception:
                raise
            else:
                self._write_unlocked(data)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self) -> dict:
        if not self.registry_path.exists():
            return {"sessions": {}}
        content = self.registry_path.read_text(encoding="utf-8").strip()
        if not content:
            return {"sessions": {}}
        payload = json.loads(content)
        payload.setdefault("sessions", {})
        return payload

    def _write_unlocked(self, payload: dict) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            dir=self.registry_path.parent,
            delete=False,
            encoding="utf-8",
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        os.replace(temp_path, self.registry_path)

    def list_sessions(self, include_closed: bool = False) -> list[SessionRecord]:
        with self._transaction() as data:
            sessions = [
                SessionRecord.from_dict(item)
                for item in data["sessions"].values()
            ]
        sessions.sort(key=lambda item: item.created_at)
        if include_closed:
            return sessions
        return [item for item in sessions if item.status != "closed"]

    def get_session(self, identifier: str, include_closed: bool = True) -> SessionRecord:
        with self._transaction() as data:
            if identifier in data["sessions"]:
                return SessionRecord.from_dict(data["sessions"][identifier])

            matches = []
            for item in data["sessions"].values():
                if item.get("name") == identifier and (include_closed or item.get("status") != "closed"):
                    matches.append(SessionRecord.from_dict(item))

        if not matches:
            raise KeyError(f"session not found: {identifier}")
        if len(matches) > 1:
            active = [item for item in matches if item.status != "closed"]
            if len(active) == 1:
                return active[0]
            raise KeyError(f"session name is ambiguous: {identifier}")
        return matches[0]

    def create_session(self, record: SessionRecord) -> None:
        with self._transaction() as data:
            if record.session_id in data["sessions"]:
                raise ValueError(f"session id already exists: {record.session_id}")
            for item in data["sessions"].values():
                if item.get("name") == record.name and item.get("status") != "closed":
                    raise ValueError(f"active session name already exists: {record.name}")
            data["sessions"][record.session_id] = record.to_dict()

    def save_session(self, record: SessionRecord) -> None:
        record.updated_at = utc_now()
        with self._transaction() as data:
            if record.session_id not in data["sessions"]:
                raise KeyError(f"session not found: {record.session_id}")
            data["sessions"][record.session_id] = record.to_dict()

    def touch_seen(self, session_id: str) -> SessionRecord:
        record = self.get_session(session_id)
        record.last_seen_at = utc_now()
        self.save_session(record)
        return record

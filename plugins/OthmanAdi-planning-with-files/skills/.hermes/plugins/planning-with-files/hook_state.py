from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import List

_MAX_SESSIONS = 256
_MAX_REMINDERS_PER_SESSION = 8
_STATE_LOCK = threading.RLock()
_SESSION_REMINDERS: OrderedDict[str, List[str]] = OrderedDict()


def state_key(project_dir: Path, session_id: str) -> str:
    project = os.path.normcase(
        os.path.realpath(os.path.abspath(project_dir.resolve(strict=True)))
    ).replace("\\", "/")
    digest = hashlib.sha256()
    for value in ("hermes", str(project), session_id):
        encoded = value.encode("utf-8", errors="surrogatepass")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def add_reminder(project_dir: Path, session_id: str, message: str) -> None:
    if not session_id or not message:
        return
    try:
        key = state_key(project_dir, session_id)
    except (OSError, RuntimeError):
        return
    with _STATE_LOCK:
        bucket = _SESSION_REMINDERS.setdefault(key, [])
        _SESSION_REMINDERS.move_to_end(key)
        if message not in bucket:
            bucket.append(message)
            del bucket[:-_MAX_REMINDERS_PER_SESSION]
        while len(_SESSION_REMINDERS) > _MAX_SESSIONS:
            _SESSION_REMINDERS.popitem(last=False)


def pop_reminders(project_dir: Path, session_id: str) -> list[str]:
    if not session_id:
        return []
    try:
        key = state_key(project_dir, session_id)
    except (OSError, RuntimeError):
        return []
    with _STATE_LOCK:
        return _SESSION_REMINDERS.pop(key, [])

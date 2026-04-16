from __future__ import annotations

import json
import time
from hashlib import sha256
from pathlib import Path
from typing import Any


class FileCache:
    def __init__(self, root: Path, ttl_seconds: int) -> None:
        self.root = root
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        digest = sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        expires_at = payload.get("expires_at", 0)
        if expires_at < time.time():
            path.unlink(missing_ok=True)
            return None
        return payload.get("value")

    def set(self, key: str, value: Any) -> None:
        path = self._path_for(key)
        payload = {
            "expires_at": time.time() + self.ttl_seconds,
            "value": value,
        }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

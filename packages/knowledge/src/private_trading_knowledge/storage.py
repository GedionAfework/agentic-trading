from __future__ import annotations

import hashlib
from pathlib import Path

from private_trading_core.config import get_settings
from private_trading_core.ids import new_id


class LocalObjectStorage:
    """Dev-friendly private object store (files on disk under data/objects)."""

    def __init__(self, root: Path | None = None) -> None:
        settings = get_settings()
        self.root = root or Path(settings.object_storage_local_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, data: bytes, *, suffix: str) -> tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        key = f"{digest[:2]}/{digest}/{new_id()}{suffix}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key, digest

    def get_bytes(self, object_key: str) -> bytes:
        path = self.root / object_key
        if not path.is_file():
            raise FileNotFoundError(object_key)
        return path.read_bytes()

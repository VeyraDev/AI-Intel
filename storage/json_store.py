"""
JSON file read/write. All modules must use this layer for file I/O.
Paths are relative to data_dir from config; no direct open() elsewhere.
"""
import json
from pathlib import Path
from typing import Any


class JSONStore:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, path: str) -> Path:
        """Resolve path under data_dir. Accept 'updates.json' or 'data/updates.json'."""
        p = Path(path)
        if not p.is_absolute() and not path.startswith("data"):
            return self.data_dir / path
        if str(p).startswith("data"):
            return self.data_dir / p.name
        return p

    def read_json(self, path: str) -> Any:
        """Read JSON file; return default if missing or invalid."""
        fp = self._path(path)
        if not fp.exists():
            return None
        try:
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def write_json(self, path: str, data: Any) -> None:
        """Write data as JSON to path under data_dir."""
        fp = self._path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: str) -> Any:
        """Alias for read_json."""
        return self.read_json(path)

    def save(self, path: str, data: Any) -> None:
        """Alias for write_json."""
        self.write_json(path, data)

"""
Persistent disk-based JSON cache for EventWatch pipeline.
Keyed by SHA-256 hash of normalized title. Enables crash recovery and eliminates redundant LLM calls.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def compute_title_hash(normalized_title: str) -> str:
    """Compute SHA-256 hexadecimal digest of normalized title."""
    return hashlib.sha256(normalized_title.strip().encode("utf-8")).hexdigest()


class DiskCache:
    """Persistent JSON cache for evaluated event titles."""

    def __init__(self, cache_file: Path | str) -> None:
        self.cache_path = Path(cache_file)
        self._entries: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """Load cache from disk if it exists."""
        if not self.cache_path.is_file():
            self._entries = {}
            return

        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    self._entries = {}
                    return
                self._entries = json.loads(content)
        except (json.JSONDecodeError, OSError):
            # If corrupt or unreadable, start fresh
            self._entries = {}

    def get(self, normalized_title: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached result by normalized title."""
        key = compute_title_hash(normalized_title)
        entry = self._entries.get(key)
        if entry:
            return entry.get("data")
        return None

    def set(self, normalized_title: str, evaluation_data: Dict[str, Any]) -> None:
        """Store evaluation result in cache."""
        key = compute_title_hash(normalized_title)
        self._entries[key] = {
            "title": normalized_title,
            "data": evaluation_data,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }

    def contains(self, normalized_title: str) -> bool:
        """Check if normalized title is present in cache."""
        key = compute_title_hash(normalized_title)
        return key in self._entries

    def save(self) -> None:
        """Persist cache to disk atomically."""
        parent_dir = self.cache_path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        # Write to temporary file in the same directory then atomic rename
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            dir=str(parent_dir),
            delete=False,
            encoding="utf-8",
        )
        try:
            json.dump(self._entries, temp_file, indent=2, ensure_ascii=False)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_file.close()
            # Atomic rename (on Windows, os.replace handles atomic overwrite)
            os.replace(temp_file.name, str(self.cache_path))
        except Exception:
            if os.path.exists(temp_file.name):
                os.remove(temp_file.name)
            raise

    def __bool__(self) -> bool:
        """Cache instance always evaluates to True, even when empty."""
        return True

    def __len__(self) -> int:
        return len(self._entries)


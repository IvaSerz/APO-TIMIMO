"""Local, compressed snapshots for repeatable inventory comparisons."""
from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
import tempfile
import uuid

from .models import Inventory

DEFAULT_HISTORY = Path.home() / ".software-audit" / "snapshots"


def list_snapshots(directory: Path | None = None) -> list[Path]:
    folder = Path(directory) if directory else DEFAULT_HISTORY
    if not folder.exists():
        return []
    return sorted(folder.glob("scan-*.json.gz"), reverse=True)


def load_snapshot(path: Path) -> Inventory:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return Inventory.from_dict(json.load(handle))


def latest_snapshot(directory: Path | None = None) -> Inventory | None:
    for path in list_snapshots(directory):
        try:
            return load_snapshot(path)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def save_snapshot(inventory: Inventory, directory: Path | None = None, keep: int = 25) -> Path:
    folder = Path(directory) if directory else DEFAULT_HISTORY
    folder.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            folder.chmod(0o700)
        except OSError:
            pass
    timestamp = inventory.scanned_at.replace("-", "").replace(":", "").replace("+", "p")
    target = folder / f"scan-{timestamp}-{uuid.uuid4().hex[:8]}.json.gz"
    file_descriptor, temp_name = tempfile.mkstemp(prefix=".scan-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(file_descriptor, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6) as compressed:
                compressed.write(json.dumps(inventory.to_dict(), ensure_ascii=False).encode("utf-8"))
        if os.name != "nt":
            os.chmod(temp_name, 0o600)
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    for obsolete in list_snapshots(folder)[max(1, keep):]:
        try:
            obsolete.unlink()
        except OSError:
            pass
    return target

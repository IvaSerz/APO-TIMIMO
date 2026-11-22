"""Domain objects and normalization for software inventory snapshots."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import re
import socket
import platform


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


@dataclass
class Software:
    name: str
    version: str = ""
    publisher: str = ""
    source: str = ""
    install_path: str = ""
    installed_at: str = ""
    identifier: str = ""
    scope: str = ""

    def stable_key(self) -> str:
        """Identify a product across version changes, without claiming it is globally unique."""
        name = normalize(self.name)
        publisher = normalize(self.publisher)
        # Use an application identifier where possible, otherwise name/publisher.
        token = normalize(self.identifier) if self.identifier else f"{name}|{publisher}"
        # Distinguish separate installations of the same app only if both are known.
        if self.install_path and not self.identifier:
            token += "|" + normalize(self.install_path.rstrip("/\\"))
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:20]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "Software":
        return cls(**{key: str(value.get(key) or "") for key in cls.__dataclass_fields__})


@dataclass
class Inventory:
    scanned_at: str = field(default_factory=utc_now)
    hostname: str = field(default_factory=socket.gethostname)
    operating_system: str = field(default_factory=lambda: f"{platform.system()} {platform.release()}")
    records: list[Software] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"schema_version": 1, "scanned_at": self.scanned_at,
                "hostname": self.hostname, "operating_system": self.operating_system,
                "records": [item.to_dict() for item in self.records],
                "warnings": self.warnings, "methods": self.methods}

    @classmethod
    def from_dict(cls, data: dict) -> "Inventory":
        if data.get("schema_version") != 1:
            raise ValueError("Неподдерживаемая версия формата инвентаризации")
        return cls(scanned_at=data["scanned_at"], hostname=data.get("hostname", ""),
                   operating_system=data.get("operating_system", ""),
                   records=[Software.from_dict(r) for r in data.get("records", [])],
                   warnings=list(data.get("warnings", [])),
                   methods=list(data.get("methods", [])))


def deduplicate(items: list[Software]) -> list[Software]:
    """Collapse exact duplicate app/package records without hiding different versions."""
    found: dict[tuple[str, str, str], Software] = {}
    for item in items:
        if not item.name.strip():
            continue
        # Never merge two different paths or versions. Same location might be found
        # by more than one macOS inventory source.
        path_or_id = normalize(item.install_path) if item.install_path else normalize(item.identifier)
        token = (normalize(item.name), normalize(item.version), path_or_id)
        old = found.get(token)
        if old is None:
            found[token] = item
        else:
            for key in ("publisher", "install_path", "installed_at", "identifier", "scope"):
                if not getattr(old, key) and getattr(item, key):
                    setattr(old, key, getattr(item, key))
            sources = set(old.source.split("; ")) | set(item.source.split("; "))
            old.source = "; ".join(sorted(s for s in sources if s))
    return sorted(found.values(), key=lambda i: (normalize(i.name), normalize(i.version), normalize(i.source)))


@dataclass
class ChangeSet:
    added: list[Software] = field(default_factory=list)
    removed: list[Software] = field(default_factory=list)
    updated: list[tuple[Software, Software]] = field(default_factory=list)


def compare(previous: Inventory, current: Inventory) -> ChangeSet:
    """Version changes and install/removal events; best-effort product matching."""
    old_map: dict[str, Software] = {r.stable_key(): r for r in previous.records}
    new_map: dict[str, Software] = {r.stable_key(): r for r in current.records}
    changes = ChangeSet()
    for key, newer in new_map.items():
        earlier = old_map.get(key)
        if earlier is None:
            changes.added.append(newer)
        elif normalize(earlier.version) != normalize(newer.version):
            changes.updated.append((earlier, newer))
    for key, earlier in old_map.items():
        if key not in new_map:
            changes.removed.append(earlier)
    return changes

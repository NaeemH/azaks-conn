"""Local state file tracking aksc-managed kubeconfig aliases.

A separate state file (~/.kube/azaks-conn/.aliases.json) is preferable to
grepping ~/.kube/config because:
  - kubectl context names aren't unique to aksc; users add contexts manually
  - we want to remember metadata (cluster name, RG, sub, admin flag, timestamp)
  - `aksc rm` must not delete contexts the user added themselves

The state file is atomically written with 0600 perms, same pattern as kubeconfig
snapshots. Round-trip is JSON for grep-ability and forward-compat.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from azaks_conn.errors import KubeconfigWriteError


@dataclass
class AliasRecord:
    """Metadata for one aksc-managed alias."""

    cluster: str
    resource_group: str | None = None
    subscription: str | None = None
    admin: bool = False
    added_at: str = ""


def state_file() -> Path:
    """`~/.kube/azaks-conn/.aliases.json` — the on-disk state file."""
    return Path.home() / ".kube" / "azaks-conn" / ".aliases.json"


def now_iso() -> str:
    """UTC RFC3339 timestamp with second resolution and `Z` suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load() -> dict[str, AliasRecord]:
    """Read the state file. Missing or empty file -> empty dict."""
    path = state_file()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text() or "{}")
    except (OSError, json.JSONDecodeError) as exc:
        raise KubeconfigWriteError(f"failed to read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise KubeconfigWriteError(f"{path} is not a valid aksc state file")
    aliases_raw: Any = raw.get("aliases") or {}
    if not isinstance(aliases_raw, dict):
        return {}
    out: dict[str, AliasRecord] = {}
    for name, rec in aliases_raw.items():
        if not isinstance(name, str) or not isinstance(rec, dict):
            continue
        out[name] = AliasRecord(
            cluster=str(rec.get("cluster", "")),
            resource_group=rec.get("resource_group"),
            subscription=rec.get("subscription"),
            admin=bool(rec.get("admin", False)),
            added_at=str(rec.get("added_at", "")),
        )
    return out


def save(aliases: dict[str, AliasRecord]) -> None:
    """Atomically persist `aliases` to the state file with 0600 perms."""
    path = state_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise KubeconfigWriteError(f"failed to create {path.parent}: {exc}") from exc

    data = {"aliases": {name: asdict(rec) for name, rec in aliases.items()}}
    try:
        fd, tmp_str = tempfile.mkstemp(prefix=".aliases-", suffix=".tmp", dir=path.parent)
    except OSError as exc:
        raise KubeconfigWriteError(f"failed to open tempfile in {path.parent}: {exc}") from exc

    tmp = Path(tmp_str)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise KubeconfigWriteError(f"failed to write {path}: {exc}") from exc
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def upsert(name: str, rec: AliasRecord) -> None:
    """Add or replace a single alias record."""
    aliases = load()
    aliases[name] = rec
    save(aliases)


def remove(name: str) -> bool:
    """Drop a single alias from state. Returns True iff it existed."""
    aliases = load()
    if name not in aliases:
        return False
    del aliases[name]
    save(aliases)
    return True

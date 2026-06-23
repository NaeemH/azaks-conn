"""Kubeconfig manipulation: rename entries, atomic write, KUBECONFIG-style merge."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, cast

import yaml

from azaks_conn.errors import KubeconfigWriteError


def default_alias_dir() -> Path:
    """`~/.kube/azaks-conn/` — per-alias snapshot directory."""
    return Path.home() / ".kube" / "azaks-conn"


def default_kubeconfig() -> Path:
    """`~/.kube/config` — the merged main kubeconfig."""
    return Path.home() / ".kube" / "config"


def rename_entries(cfg: dict[str, Any], alias: str) -> dict[str, Any]:
    """Rewrite cluster/user/context names in `cfg` to `alias`.

    `az aks get-credentials -n <cluster>` always emits a single-cluster
    kubeconfig (one cluster, one user, one context — the context's `--admin`
    variant has `clusterAdmin_*` user naming, but still exactly one entry).
    We keep only the first of each, rename them to `alias`, and set
    `current-context: <alias>`.

    Mutates `cfg` in place and returns it.

    Raises:
        KubeconfigWriteError: if the YAML is missing clusters/users/contexts.
    """
    clusters = cfg.get("clusters") or []
    users = cfg.get("users") or []
    contexts = cfg.get("contexts") or []
    if not clusters or not users or not contexts:
        raise KubeconfigWriteError("kubeconfig from `az` is missing clusters/users/contexts")

    cluster0 = clusters[0]
    user0 = users[0]
    ctx0 = contexts[0]

    cluster0["name"] = alias
    user0["name"] = alias
    ctx0["name"] = alias
    # Inner `context:` block points at cluster + user by name.
    inner = ctx0.setdefault("context", {})
    inner["cluster"] = alias
    inner["user"] = alias

    cfg["clusters"] = [cluster0]
    cfg["users"] = [user0]
    cfg["contexts"] = [ctx0]
    cfg["current-context"] = alias
    return cfg


def write_atomic(path: Path, cfg: dict[str, Any]) -> None:
    """Write YAML to `path` atomically with 0600 perms.

    Uses `tempfile.mkstemp(dir=path.parent)` so the rename is same-filesystem
    and therefore atomic. Cleans up the tempfile on any failure.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise KubeconfigWriteError(f"failed to create {path.parent}: {exc}") from exc

    try:
        fd, tmp_str = tempfile.mkstemp(prefix=".azaks-conn-", suffix=".tmp", dir=path.parent)
    except OSError as exc:
        raise KubeconfigWriteError(f"failed to open tempfile in {path.parent}: {exc}") from exc

    tmp = Path(tmp_str)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise KubeconfigWriteError(f"failed to write {path}: {exc}") from exc
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _load_main(path: Path) -> dict[str, Any]:
    """Load the main kubeconfig at `path`, or return an empty skeleton."""
    if not path.exists():
        return {
            "apiVersion": "v1",
            "kind": "Config",
            "preferences": {},
            "clusters": [],
            "users": [],
            "contexts": [],
        }
    try:
        loaded = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise KubeconfigWriteError(f"failed to read {path}: {exc}") from exc
    if loaded is None:
        return {
            "apiVersion": "v1",
            "kind": "Config",
            "preferences": {},
            "clusters": [],
            "users": [],
            "contexts": [],
        }
    if not isinstance(loaded, dict):
        raise KubeconfigWriteError(f"{path} is not a valid kubeconfig YAML")
    return cast(dict[str, Any], loaded)


def merge_into(
    main_path: Path,
    alias_cfg: dict[str, Any],
    alias: str,
    *,
    overwrite: bool,
) -> bool:
    """Merge `alias_cfg` into the kubeconfig at `main_path`.

    Args:
        main_path: usually `~/.kube/config`.
        alias_cfg: the renamed single-cluster YAML (output of `rename_entries`).
        alias: the alias name to look up in the existing main config.
        overwrite: if False and entries for `alias` already exist, raise.

    Returns:
        True if the alias was newly added, False if existing entries were replaced.

    Raises:
        KubeconfigWriteError: on read/write failure, malformed YAML, or
            existing-alias collision when overwrite is False.
    """
    main_cfg = _load_main(main_path)
    for key in ("clusters", "users", "contexts"):
        main_cfg.setdefault(key, [])
    main_cfg.setdefault("apiVersion", "v1")
    main_cfg.setdefault("kind", "Config")

    def _has(name: str, key: str) -> bool:
        return any(e.get("name") == name for e in main_cfg[key])

    existed = _has(alias, "clusters") or _has(alias, "users") or _has(alias, "contexts")
    if existed and not overwrite:
        raise KubeconfigWriteError(
            f"alias {alias!r} already exists in {main_path}. Pass --overwrite to replace it."
        )

    for key in ("clusters", "users", "contexts"):
        main_cfg[key] = [e for e in main_cfg[key] if e.get("name") != alias]

    main_cfg["clusters"].append(alias_cfg["clusters"][0])
    main_cfg["users"].append(alias_cfg["users"][0])
    main_cfg["contexts"].append(alias_cfg["contexts"][0])
    main_cfg["current-context"] = alias

    write_atomic(main_path, main_cfg)
    return not existed


def main_has_alias(main_path: Path, alias: str) -> bool:
    """Return True if `main_path` exists and has any entry named `alias`."""
    if not main_path.exists():
        return False
    try:
        main_cfg = _load_main(main_path)
    except KubeconfigWriteError:
        # If the kubeconfig is unparseable we can't say it has the alias.
        # Caller should probably surface the parse error separately.
        return False
    for key in ("clusters", "users", "contexts"):
        if any(e.get("name") == alias for e in main_cfg.get(key) or []):
            return True
    return False


def remove_from(main_path: Path, alias: str) -> bool:
    """Strip all entries named `alias` from the kubeconfig at `main_path`.

    Idempotent: returns False (and writes nothing) if no matching entries
    exist. If `current-context` was `alias`, clears it to `""` (kubectl
    treats empty current-context as "no default selected").

    Returns:
        True iff at least one cluster/user/context entry was removed.
    """
    if not main_path.exists():
        return False

    main_cfg = _load_main(main_path)
    removed = False
    for key in ("clusters", "users", "contexts"):
        entries = main_cfg.get(key) or []
        kept = [e for e in entries if e.get("name") != alias]
        if len(kept) != len(entries):
            removed = True
        main_cfg[key] = kept

    if main_cfg.get("current-context") == alias:
        main_cfg["current-context"] = ""

    if removed:
        write_atomic(main_path, main_cfg)
    return removed

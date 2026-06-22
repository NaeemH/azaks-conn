"""Tests for `azaks_conn.kubeconfig`."""

from __future__ import annotations

import copy
import stat
from pathlib import Path
from typing import Any

import pytest
import yaml

from azaks_conn.errors import KubeconfigWriteError
from azaks_conn.kubeconfig import (
    default_alias_dir,
    default_kubeconfig,
    merge_into,
    rename_entries,
    write_atomic,
)


# ------------------------------------------------------------- defaults ----
def test_default_alias_dir_under_home(kube_home: Path) -> None:
    assert default_alias_dir() == kube_home / ".kube" / "azaks-conn"


def test_default_kubeconfig_under_home(kube_home: Path) -> None:
    assert default_kubeconfig() == kube_home / ".kube" / "config"


# ----------------------------------------------------------- rename_entries ----
def test_rename_entries_sets_all_names(az_kubeconfig: dict[str, Any]) -> None:
    out = rename_entries(az_kubeconfig, "prod")
    assert out["clusters"][0]["name"] == "prod"
    assert out["users"][0]["name"] == "prod"
    assert out["contexts"][0]["name"] == "prod"
    assert out["contexts"][0]["context"]["cluster"] == "prod"
    assert out["contexts"][0]["context"]["user"] == "prod"
    assert out["current-context"] == "prod"


def test_rename_entries_keeps_inner_user_payload(az_kubeconfig: dict[str, Any]) -> None:
    """Only names change — the exec block and server URL must survive."""
    original_exec = az_kubeconfig["users"][0]["user"]["exec"]
    original_server = az_kubeconfig["clusters"][0]["cluster"]["server"]
    out = rename_entries(az_kubeconfig, "prod")
    assert out["users"][0]["user"]["exec"] == original_exec
    assert out["clusters"][0]["cluster"]["server"] == original_server


def test_rename_entries_rejects_malformed() -> None:
    with pytest.raises(KubeconfigWriteError, match="missing"):
        rename_entries({"apiVersion": "v1"}, "prod")
    with pytest.raises(KubeconfigWriteError, match="missing"):
        rename_entries({"clusters": [], "users": [], "contexts": []}, "prod")


# ----------------------------------------------------------- write_atomic ----
def test_write_atomic_creates_parents_and_chmods_600(
    tmp_path: Path, az_kubeconfig: dict[str, Any]
) -> None:
    target = tmp_path / "nested" / "dir" / "kubeconfig"
    write_atomic(target, az_kubeconfig)
    assert target.exists()
    perms = stat.S_IMODE(target.stat().st_mode)
    assert perms == 0o600
    loaded = yaml.safe_load(target.read_text())
    assert loaded["current-context"] == "my-cluster"


def test_write_atomic_overwrites_existing(tmp_path: Path, az_kubeconfig: dict[str, Any]) -> None:
    target = tmp_path / "kubeconfig"
    target.write_text("garbage: true\n")
    write_atomic(target, az_kubeconfig)
    loaded = yaml.safe_load(target.read_text())
    assert loaded["current-context"] == "my-cluster"


def test_write_atomic_leaves_no_temp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If yaml.safe_dump blows up, no .azaks-conn-*.tmp file should be left."""
    target = tmp_path / "kubeconfig"

    def _explode(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr("azaks_conn.kubeconfig.yaml.safe_dump", _explode)
    with pytest.raises(RuntimeError, match="disk full"):
        write_atomic(target, {"apiVersion": "v1"})
    leftovers = list(tmp_path.glob(".azaks-conn-*.tmp"))
    assert leftovers == [], f"tempfile not cleaned: {leftovers}"


# ----------------------------------------------------------- merge_into ----
def _renamed(cfg: dict[str, Any], alias: str) -> dict[str, Any]:
    return rename_entries(copy.deepcopy(cfg), alias)


def test_merge_into_creates_new_kubeconfig(kube_home: Path, az_kubeconfig: dict[str, Any]) -> None:
    target = kube_home / "config"
    alias_cfg = _renamed(az_kubeconfig, "prod")
    added = merge_into(target, alias_cfg, "prod", overwrite=False)
    assert added is True
    main = yaml.safe_load(target.read_text())
    assert main["current-context"] == "prod"
    assert [c["name"] for c in main["clusters"]] == ["prod"]
    assert [u["name"] for u in main["users"]] == ["prod"]
    assert [c["name"] for c in main["contexts"]] == ["prod"]


def test_merge_into_preserves_unrelated_entries(
    kube_home: Path, az_kubeconfig: dict[str, Any]
) -> None:
    target = kube_home / "config"
    target.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "v1",
                "kind": "Config",
                "clusters": [{"name": "other", "cluster": {"server": "https://other"}}],
                "users": [{"name": "other", "user": {"token": "T"}}],
                "contexts": [{"name": "other", "context": {"cluster": "other", "user": "other"}}],
                "current-context": "other",
            }
        )
    )
    alias_cfg = _renamed(az_kubeconfig, "prod")
    added = merge_into(target, alias_cfg, "prod", overwrite=False)
    assert added is True
    main = yaml.safe_load(target.read_text())
    cluster_names = {c["name"] for c in main["clusters"]}
    assert cluster_names == {"other", "prod"}
    assert main["current-context"] == "prod"


def test_merge_into_refuses_existing_without_overwrite(
    kube_home: Path, az_kubeconfig: dict[str, Any]
) -> None:
    target = kube_home / "config"
    alias_cfg = _renamed(az_kubeconfig, "prod")
    merge_into(target, alias_cfg, "prod", overwrite=False)
    # Second merge with same alias must fail.
    with pytest.raises(KubeconfigWriteError, match="already exists"):
        merge_into(target, alias_cfg, "prod", overwrite=False)


def test_merge_into_overwrite_replaces(kube_home: Path, az_kubeconfig: dict[str, Any]) -> None:
    target = kube_home / "config"
    first = _renamed(az_kubeconfig, "prod")
    first["clusters"][0]["cluster"]["server"] = "https://OLD:443"
    merge_into(target, first, "prod", overwrite=False)
    # New credentials for the same alias.
    second = _renamed(az_kubeconfig, "prod")
    second["clusters"][0]["cluster"]["server"] = "https://NEW:443"
    added = merge_into(target, second, "prod", overwrite=True)
    assert added is False
    main = yaml.safe_load(target.read_text())
    # Exactly one entry per kind for `prod`, and it points at NEW.
    prod_clusters = [c for c in main["clusters"] if c["name"] == "prod"]
    assert len(prod_clusters) == 1
    assert prod_clusters[0]["cluster"]["server"] == "https://NEW:443"


def test_merge_into_rejects_garbage_kubeconfig(
    kube_home: Path, az_kubeconfig: dict[str, Any]
) -> None:
    target = kube_home / "config"
    target.write_text("just-a-string\n")
    alias_cfg = _renamed(az_kubeconfig, "prod")
    with pytest.raises(KubeconfigWriteError, match="not a valid kubeconfig"):
        merge_into(target, alias_cfg, "prod", overwrite=False)


def test_merge_into_handles_empty_main(kube_home: Path, az_kubeconfig: dict[str, Any]) -> None:
    """An empty file (yaml.safe_load -> None) should be treated like a fresh start."""
    target = kube_home / "config"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("")
    alias_cfg = _renamed(az_kubeconfig, "prod")
    added = merge_into(target, alias_cfg, "prod", overwrite=False)
    assert added is True
    main = yaml.safe_load(target.read_text())
    assert main["current-context"] == "prod"

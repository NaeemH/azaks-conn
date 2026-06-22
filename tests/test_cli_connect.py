"""End-to-end tests for `aksc connect`."""

from __future__ import annotations

import copy
import stat
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from azaks_conn.cli import app

runner = CliRunner()


def _patch_get_credentials(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    *,
    record: list[dict[str, Any]] | None = None,
) -> None:
    """Replace `aks.get_credentials` (as imported by cli.py) with a stub."""

    def _stub(
        cluster: str,
        *,
        resource_group: str | None = None,
        subscription: str | None = None,
        admin: bool = False,
    ) -> dict[str, Any]:
        if record is not None:
            record.append(
                {
                    "cluster": cluster,
                    "resource_group": resource_group,
                    "subscription": subscription,
                    "admin": admin,
                }
            )
        return copy.deepcopy(payload)

    # cli.py does `from azaks_conn.aks import get_credentials`, so we have to
    # patch the *reference* it captured, not the source module.
    monkeypatch.setattr("azaks_conn.cli.get_credentials", _stub)


def test_connect_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    _patch_get_credentials(monkeypatch, az_kubeconfig)
    result = runner.invoke(app, ["connect", "my-cluster", "--alias", "prod"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    snapshot = kube_home / ".kube" / "azaks-conn" / "prod"
    main = kube_home / ".kube" / "config"
    assert snapshot.exists()
    assert main.exists()
    assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600
    assert stat.S_IMODE(main.stat().st_mode) == 0o600

    main_cfg = yaml.safe_load(main.read_text())
    assert main_cfg["current-context"] == "prod"
    assert [c["name"] for c in main_cfg["clusters"]] == ["prod"]


def test_connect_uses_cluster_as_default_alias(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    _patch_get_credentials(monkeypatch, az_kubeconfig)
    result = runner.invoke(app, ["connect", "my-cluster"])
    assert result.exit_code == 0
    snapshot = kube_home / ".kube" / "azaks-conn" / "my-cluster"
    assert snapshot.exists()
    main_cfg = yaml.safe_load((kube_home / ".kube" / "config").read_text())
    assert main_cfg["current-context"] == "my-cluster"


def test_connect_passes_locators_and_admin(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    record: list[dict[str, Any]] = []
    _patch_get_credentials(monkeypatch, az_kubeconfig, record=record)
    result = runner.invoke(
        app,
        [
            "connect",
            "my-cluster",
            "-s",
            "sub-123",
            "-g",
            "my-rg",
            "--admin",
        ],
    )
    assert result.exit_code == 0
    assert record == [
        {
            "cluster": "my-cluster",
            "resource_group": "my-rg",
            "subscription": "sub-123",
            "admin": True,
        }
    ]


def test_connect_env_var_fallback(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    """-s / -g default to AZURE_SUBSCRIPTION_ID / AZURE_RESOURCE_GROUP env vars."""
    record: list[dict[str, Any]] = []
    _patch_get_credentials(monkeypatch, az_kubeconfig, record=record)
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "env-sub")
    monkeypatch.setenv("AZURE_RESOURCE_GROUP", "env-rg")
    result = runner.invoke(app, ["connect", "my-cluster"])
    assert result.exit_code == 0
    assert record[0]["subscription"] == "env-sub"
    assert record[0]["resource_group"] == "env-rg"


def test_connect_refuses_existing_without_overwrite(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    _patch_get_credentials(monkeypatch, az_kubeconfig)
    # First connect succeeds.
    r1 = runner.invoke(app, ["connect", "my-cluster", "--alias", "prod"])
    assert r1.exit_code == 0
    # Second without --overwrite must exit 2 with an "already exists" error on stderr.
    r2 = runner.invoke(app, ["connect", "my-cluster", "--alias", "prod"])
    assert r2.exit_code == 2
    combined = (r2.stdout or "") + (r2.stderr or "")
    assert "already exists" in combined


def test_connect_overwrite_replaces(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    _patch_get_credentials(monkeypatch, az_kubeconfig)
    runner.invoke(app, ["connect", "my-cluster", "--alias", "prod"])
    # Change the payload — simulate fresh credentials.
    az_kubeconfig["clusters"][0]["cluster"]["server"] = "https://NEW.example:443"
    _patch_get_credentials(monkeypatch, az_kubeconfig)
    r = runner.invoke(app, ["connect", "my-cluster", "--alias", "prod", "--overwrite"])
    assert r.exit_code == 0
    main_cfg = yaml.safe_load((kube_home / ".kube" / "config").read_text())
    prod = [c for c in main_cfg["clusters"] if c["name"] == "prod"]
    assert len(prod) == 1
    assert prod[0]["cluster"]["server"] == "https://NEW.example:443"


def test_connect_admin_prints_warning(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    _patch_get_credentials(monkeypatch, az_kubeconfig)
    r = runner.invoke(app, ["connect", "my-cluster", "--alias", "prod", "--admin"])
    assert r.exit_code == 0
    # Warning goes to stderr per Console(stderr=True).
    combined = (r.stdout or "") + (r.stderr or "")
    assert "admin" in combined.lower()


def test_connect_propagates_aks_error(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
) -> None:
    from azaks_conn.errors import ClusterNotFoundError

    def _stub(cluster: str, **_: Any) -> dict[str, Any]:
        raise ClusterNotFoundError(f"cluster {cluster!r} not found")

    monkeypatch.setattr("azaks_conn.cli.get_credentials", _stub)
    r = runner.invoke(app, ["connect", "ghost"])
    assert r.exit_code == 2
    combined = (r.stdout or "") + (r.stderr or "")
    assert "not found" in combined

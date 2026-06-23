"""End-to-end tests for `aksc refresh`."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from azaks_conn import config
from azaks_conn.aks import AksAccessError
from azaks_conn.cli import app
from azaks_conn.config import AliasRecord

runner = CliRunner()


def _seed_state(records: dict[str, AliasRecord]) -> None:
    config.save(records)


def test_refresh_unknown_alias(kube_home: Path) -> None:
    result = runner.invoke(app, ["refresh", "ghost"])
    assert result.exit_code == 2
    combined = (result.stdout or "") + (result.stderr or "")
    assert "no aksc-managed alias" in combined


def test_refresh_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    """Refresh of a known alias re-fetches, replaces snapshot + kubeconfig, bumps added_at."""
    _seed_state(
        {
            "prod": AliasRecord(
                cluster="prod-cluster",
                resource_group="rg-prod",
                subscription="sub-1",
                admin=False,
                added_at="2026-01-01T00:00:00Z",
            )
        }
    )

    captured: dict[str, Any] = {}

    def _stub(
        cluster: str,
        *,
        resource_group: str | None = None,
        subscription: str | None = None,
        admin: bool = False,
    ) -> dict[str, Any]:
        captured["cluster"] = cluster
        captured["resource_group"] = resource_group
        captured["subscription"] = subscription
        captured["admin"] = admin
        return copy.deepcopy(az_kubeconfig)

    monkeypatch.setattr("azaks_conn.cli.get_credentials", _stub)
    result = runner.invoke(app, ["refresh", "prod"])
    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    # get_credentials called with the recorded metadata.
    assert captured == {
        "cluster": "prod-cluster",
        "resource_group": "rg-prod",
        "subscription": "sub-1",
        "admin": False,
    }

    # Snapshot exists with mode 0600.
    snapshot = kube_home / ".kube" / "azaks-conn" / "prod"
    assert snapshot.exists()
    assert oct(snapshot.stat().st_mode & 0o777) == "0o600"

    # Main kubeconfig has the renamed entries + current-context = prod.
    main_cfg = yaml.safe_load((kube_home / ".kube" / "config").read_text())
    assert main_cfg["current-context"] == "prod"
    assert any(c["name"] == "prod" for c in main_cfg["clusters"])

    # State entry preserved with bumped added_at.
    rec = config.load()["prod"]
    assert rec.cluster == "prod-cluster"
    assert rec.resource_group == "rg-prod"
    assert rec.subscription == "sub-1"
    assert rec.admin is False
    assert rec.added_at != "2026-01-01T00:00:00Z"


def test_refresh_replaces_existing_kubeconfig_entry(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    """Refresh must overwrite a stale kubeconfig entry without --overwrite flag."""
    main = kube_home / ".kube" / "config"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "v1",
                "kind": "Config",
                "clusters": [{"name": "prod", "cluster": {"server": "https://STALE.example:443"}}],
                "users": [{"name": "prod", "user": {"token": "STALE"}}],
                "contexts": [{"name": "prod", "context": {"cluster": "prod", "user": "prod"}}],
                "current-context": "other",
            }
        )
    )
    _seed_state({"prod": AliasRecord(cluster="prod-cluster", added_at="t")})

    fresh = copy.deepcopy(az_kubeconfig)
    fresh["clusters"][0]["cluster"]["server"] = "https://FRESH.example:443"

    monkeypatch.setattr("azaks_conn.cli.get_credentials", lambda *_a, **_k: fresh)
    result = runner.invoke(app, ["refresh", "prod"])
    assert result.exit_code == 0

    main_cfg = yaml.safe_load(main.read_text())
    prod_entries = [c for c in main_cfg["clusters"] if c["name"] == "prod"]
    assert len(prod_entries) == 1
    assert prod_entries[0]["cluster"]["server"] == "https://FRESH.example:443"
    # current-context switched to the refreshed alias.
    assert main_cfg["current-context"] == "prod"


def test_refresh_preserves_admin_flag(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    """Refresh of an admin alias passes admin=True through and reprints the warning."""
    _seed_state(
        {
            "prod": AliasRecord(
                cluster="prod-cluster",
                resource_group="rg-prod",
                admin=True,
                added_at="t",
            )
        }
    )

    captured: dict[str, Any] = {}

    def _stub(
        cluster: str,
        *,
        resource_group: str | None = None,
        subscription: str | None = None,
        admin: bool = False,
    ) -> dict[str, Any]:
        captured["admin"] = admin
        return copy.deepcopy(az_kubeconfig)

    monkeypatch.setattr("azaks_conn.cli.get_credentials", _stub)
    result = runner.invoke(app, ["refresh", "prod"])
    assert result.exit_code == 0
    assert captured["admin"] is True
    combined = (result.stdout or "") + (result.stderr or "")
    assert "cluster-admin" in combined
    assert "warning" in combined.lower()
    # admin flag preserved in state after refresh.
    assert config.load()["prod"].admin is True


def test_refresh_no_warning_for_non_admin(
    monkeypatch: pytest.MonkeyPatch,
    kube_home: Path,
    az_kubeconfig: dict[str, Any],
) -> None:
    _seed_state({"prod": AliasRecord(cluster="prod-cluster", added_at="t")})
    monkeypatch.setattr(
        "azaks_conn.cli.get_credentials", lambda *_a, **_k: copy.deepcopy(az_kubeconfig)
    )
    result = runner.invoke(app, ["refresh", "prod"])
    assert result.exit_code == 0
    combined = (result.stdout or "") + (result.stderr or "")
    assert "cluster-admin" not in combined


def test_refresh_propagates_aks_error(monkeypatch: pytest.MonkeyPatch, kube_home: Path) -> None:
    """If `az aks get-credentials` fails, refresh exits 2 without touching state."""
    _seed_state(
        {
            "prod": AliasRecord(
                cluster="prod-cluster",
                added_at="2026-01-01T00:00:00Z",
            )
        }
    )

    def _boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise AksAccessError("az failed: subscription not registered")

    monkeypatch.setattr("azaks_conn.cli.get_credentials", _boom)
    result = runner.invoke(app, ["refresh", "prod"])
    assert result.exit_code == 2
    combined = (result.stdout or "") + (result.stderr or "")
    assert "subscription not registered" in combined
    # State left untouched (added_at unchanged).
    assert config.load()["prod"].added_at == "2026-01-01T00:00:00Z"

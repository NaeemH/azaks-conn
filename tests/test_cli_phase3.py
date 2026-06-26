"""End-to-end tests for `aksc list`, `aksc verify`, and `aksc rm`."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from azaks_conn import config
from azaks_conn.cli import app
from azaks_conn.config import AliasRecord
from azaks_conn.errors import KubectlNotFoundError, KubectlProbeError

runner = CliRunner()


def _seed_state(records: dict[str, AliasRecord]) -> None:
    config.save(records)


# ==========================================================================
# list
# ==========================================================================
def test_list_empty(kube_home: Path) -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "no aksc-managed aliases" in result.stdout


def test_list_populated(kube_home: Path) -> None:
    _seed_state(
        {
            "prod": AliasRecord(
                cluster="prod-cluster",
                resource_group="rg-prod",
                subscription="sub-1",
                admin=False,
                added_at="2026-06-23T08:00:00Z",
            ),
            "stage": AliasRecord(
                cluster="stage-cluster",
                admin=True,
                added_at="2026-06-23T09:00:00Z",
            ),
        }
    )
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "prod" in result.stdout
    assert "prod-cluster" in result.stdout
    assert "stage" in result.stdout
    assert "stage-cluster" in result.stdout


def test_list_surfaces_corrupt_state(kube_home: Path) -> None:
    sf = config.state_file()
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text("{garbage")
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 2
    combined = (result.stdout or "") + (result.stderr or "")
    assert "failed to read" in combined or "error" in combined.lower()


def test_list_marks_admin_alias(kube_home: Path) -> None:
    """Admin aliases must be visually flagged so they aren't mistaken for AAD ones."""
    _seed_state(
        {
            "safe": AliasRecord(cluster="c1", admin=False, added_at="t"),
            "danger": AliasRecord(cluster="c2", admin=True, added_at="t"),
        }
    )
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    # The admin row should contain the literal "ADMIN" marker (Rich strips
    # markup when stdout is not a TTY, so the bare word survives).
    assert "ADMIN" in result.stdout


def test_list_json_empty(kube_home: Path) -> None:
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_list_json_populated(kube_home: Path) -> None:
    _seed_state(
        {
            "prod": AliasRecord(
                cluster="prod-cluster",
                resource_group="rg-prod",
                subscription="00000000-0000-0000-0000-000000000001",
                admin=True,
                added_at="2026-06-25T08:00:00Z",
            ),
        }
    )
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == [
        {
            "alias": "prod",
            "cluster": "prod-cluster",
            "resource_group": "rg-prod",
            "subscription": "00000000-0000-0000-0000-000000000001",
            "admin": True,
            "added_at": "2026-06-25T08:00:00Z",
        }
    ]


def test_list_non_tty_does_not_truncate(kube_home: Path) -> None:
    """Piped output must keep the full subscription id and timestamp (issue #8)."""
    sub = "00000000-0000-0000-0000-000000000abc"
    ts = "2026-06-25T08:00:00Z"
    _seed_state(
        {
            "prod": AliasRecord(
                cluster="prod-cluster",
                resource_group="rg-prod",
                subscription=sub,
                added_at=ts,
            ),
        }
    )
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert sub in result.stdout
    assert ts in result.stdout
    assert "…" not in result.stdout


# ==========================================================================
# verify
# ==========================================================================
def test_verify_unknown_alias(kube_home: Path) -> None:
    result = runner.invoke(app, ["verify", "ghost"])
    assert result.exit_code == 2
    combined = (result.stdout or "") + (result.stderr or "")
    assert "no aksc-managed alias" in combined


def test_verify_happy_path(monkeypatch: pytest.MonkeyPatch, kube_home: Path) -> None:
    _seed_state({"prod": AliasRecord(cluster="prod-cluster", added_at="t")})

    def _stub(context: str, *, timeout_seconds: int = 10) -> str:
        assert context == "prod"
        return (
            "Kubernetes control plane is running at https://prod.example:443\n"
            "CoreDNS is running at https://prod.example:443/api/...\n"
        )

    monkeypatch.setattr("azaks_conn.cli.kubectl.cluster_info", _stub)
    result = runner.invoke(app, ["verify", "prod"])
    assert result.exit_code == 0
    assert "reachable" in result.stdout
    assert "control plane" in result.stdout


def test_verify_kubectl_failure(monkeypatch: pytest.MonkeyPatch, kube_home: Path) -> None:
    _seed_state({"prod": AliasRecord(cluster="prod-cluster", added_at="t")})

    def _stub(context: str, *, timeout_seconds: int = 10) -> str:
        raise KubectlProbeError(f"probe failed for {context!r}: token expired")

    monkeypatch.setattr("azaks_conn.cli.kubectl.cluster_info", _stub)
    result = runner.invoke(app, ["verify", "prod"])
    assert result.exit_code == 2
    combined = (result.stdout or "") + (result.stderr or "")
    assert "token expired" in combined


def test_verify_kubectl_missing(monkeypatch: pytest.MonkeyPatch, kube_home: Path) -> None:
    _seed_state({"prod": AliasRecord(cluster="prod-cluster", added_at="t")})

    def _stub(context: str, *, timeout_seconds: int = 10) -> str:
        raise KubectlNotFoundError("`kubectl` not on PATH")

    monkeypatch.setattr("azaks_conn.cli.kubectl.cluster_info", _stub)
    result = runner.invoke(app, ["verify", "prod"])
    assert result.exit_code == 2
    combined = (result.stdout or "") + (result.stderr or "")
    assert "kubectl" in combined and "PATH" in combined


def test_verify_passes_timeout(monkeypatch: pytest.MonkeyPatch, kube_home: Path) -> None:
    _seed_state({"prod": AliasRecord(cluster="prod-cluster", added_at="t")})
    captured: dict[str, int] = {}

    def _stub(context: str, *, timeout_seconds: int = 10) -> str:
        captured["timeout"] = timeout_seconds
        return "Kubernetes control plane is running at https://x"

    monkeypatch.setattr("azaks_conn.cli.kubectl.cluster_info", _stub)
    result = runner.invoke(app, ["verify", "prod", "--timeout", "30"])
    assert result.exit_code == 0
    assert captured["timeout"] == 30


def test_verify_warns_on_admin_alias(monkeypatch: pytest.MonkeyPatch, kube_home: Path) -> None:
    """A successful verify of a --admin alias must reprint the bypass warning."""
    _seed_state({"prod": AliasRecord(cluster="prod-cluster", admin=True, added_at="t")})

    def _stub(context: str, *, timeout_seconds: int = 10) -> str:
        return "Kubernetes control plane is running at https://prod:443"

    monkeypatch.setattr("azaks_conn.cli.kubectl.cluster_info", _stub)
    result = runner.invoke(app, ["verify", "prod"])
    assert result.exit_code == 0
    combined = (result.stdout or "") + (result.stderr or "")
    assert "cluster-admin" in combined
    assert "warning" in combined.lower()


def test_verify_no_warning_for_non_admin(monkeypatch: pytest.MonkeyPatch, kube_home: Path) -> None:
    """Non-admin (AAD) aliases must NOT trigger the cluster-admin warning."""
    _seed_state({"prod": AliasRecord(cluster="prod-cluster", admin=False, added_at="t")})

    def _stub(context: str, *, timeout_seconds: int = 10) -> str:
        return "Kubernetes control plane is running at https://prod:443"

    monkeypatch.setattr("azaks_conn.cli.kubectl.cluster_info", _stub)
    result = runner.invoke(app, ["verify", "prod"])
    assert result.exit_code == 0
    combined = (result.stdout or "") + (result.stderr or "")
    assert "cluster-admin" not in combined


# ==========================================================================
# rm
# ==========================================================================
def _seed_full(kube_home: Path, az_kubeconfig: dict[str, Any], alias: str) -> None:
    """Simulate a prior `aksc connect <c> --alias <alias>` by populating all 3."""
    from azaks_conn.kubeconfig import default_alias_dir, merge_into, rename_entries, write_atomic

    renamed = rename_entries(copy.deepcopy(az_kubeconfig), alias)
    write_atomic(default_alias_dir() / alias, renamed)
    merge_into(kube_home / ".kube" / "config", renamed, alias, overwrite=False)
    config.upsert(alias, AliasRecord(cluster="prod-cluster", added_at="t"))


def test_rm_full_cleanup(kube_home: Path, az_kubeconfig: dict[str, Any]) -> None:
    _seed_full(kube_home, az_kubeconfig, "prod")
    result = runner.invoke(app, ["rm", "prod", "--force"])
    assert result.exit_code == 0
    # state: gone
    assert "prod" not in config.load()
    # snapshot: gone
    assert not (kube_home / ".kube" / "azaks-conn" / "prod").exists()
    # main kubeconfig: no entry named prod, current-context cleared
    main_cfg = yaml.safe_load((kube_home / ".kube" / "config").read_text())
    assert all(c["name"] != "prod" for c in main_cfg.get("clusters") or [])
    assert main_cfg.get("current-context") == ""


def test_rm_idempotent_on_missing(kube_home: Path) -> None:
    result = runner.invoke(app, ["rm", "ghost", "--force"])
    # Soft warning, exit 0 — `aksc rm ghost` is a no-op that prints a hint.
    assert result.exit_code == 0
    combined = (result.stdout or "") + (result.stderr or "")
    assert "no traces" in combined.lower() or "nothing to do" in combined.lower()


def test_rm_partial_state_only(kube_home: Path) -> None:
    """If only the state has the alias (e.g. user nuked their kubeconfig manually),
    rm still cleans up state."""
    _seed_state({"prod": AliasRecord(cluster="prod-cluster", added_at="t")})
    result = runner.invoke(app, ["rm", "prod", "--force"])
    assert result.exit_code == 0
    assert "prod" not in config.load()


def test_rm_partial_snapshot_only(kube_home: Path) -> None:
    """Stray snapshot file without state entry: rm should still delete it."""
    from azaks_conn.kubeconfig import default_alias_dir, write_atomic

    write_atomic(
        default_alias_dir() / "orphan",
        {
            "apiVersion": "v1",
            "kind": "Config",
            "clusters": [{"name": "orphan", "cluster": {"server": "x"}}],
            "users": [{"name": "orphan", "user": {}}],
            "contexts": [{"name": "orphan", "context": {"cluster": "orphan", "user": "orphan"}}],
            "current-context": "orphan",
        },
    )
    snapshot = default_alias_dir() / "orphan"
    assert snapshot.exists()
    result = runner.invoke(app, ["rm", "orphan", "--force"])
    assert result.exit_code == 0
    assert not snapshot.exists()


def test_rm_preserves_unrelated_contexts(kube_home: Path, az_kubeconfig: dict[str, Any]) -> None:
    """rm of one alias must NOT touch other entries in ~/.kube/config."""
    main = kube_home / ".kube" / "config"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text(
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
    _seed_full(kube_home, az_kubeconfig, "prod")

    result = runner.invoke(app, ["rm", "prod", "--force"])
    assert result.exit_code == 0

    main_cfg = yaml.safe_load(main.read_text())
    cluster_names = {c["name"] for c in main_cfg["clusters"]}
    assert cluster_names == {"other"}
    # current-context was set to prod by _seed_full → cleared by rm.
    assert main_cfg["current-context"] == ""


def test_rm_confirms_then_aborts(kube_home: Path, az_kubeconfig: dict[str, Any]) -> None:
    """Without --force, an empty/no answer aborts."""
    _seed_full(kube_home, az_kubeconfig, "prod")
    # CliRunner's `input="n\n"` answers the confirm with no.
    result = runner.invoke(app, ["rm", "prod"], input="n\n")
    assert result.exit_code != 0
    # state still has it
    assert "prod" in config.load()
    # snapshot still there
    assert (kube_home / ".kube" / "azaks-conn" / "prod").exists()


def test_rm_confirms_then_proceeds(kube_home: Path, az_kubeconfig: dict[str, Any]) -> None:
    """Without --force, a 'y' answer proceeds."""
    _seed_full(kube_home, az_kubeconfig, "prod")
    result = runner.invoke(app, ["rm", "prod"], input="y\n")
    assert result.exit_code == 0
    assert "prod" not in config.load()


# ==========================================================================
# connect (extension): verify state-upsert side effect
# ==========================================================================
def test_connect_records_state(
    monkeypatch: pytest.MonkeyPatch, kube_home: Path, az_kubeconfig: dict[str, Any]
) -> None:
    def _stub(
        cluster: str,
        *,
        resource_group: str | None = None,
        subscription: str | None = None,
        admin: bool = False,
    ) -> dict[str, Any]:
        return copy.deepcopy(az_kubeconfig)

    monkeypatch.setattr("azaks_conn.cli.get_credentials", _stub)
    result = runner.invoke(
        app,
        ["connect", "prod-cluster", "--alias", "prod", "-g", "rg-prod", "-s", "sub-1"],
    )
    assert result.exit_code == 0

    records = config.load()
    assert "prod" in records
    rec = records["prod"]
    assert rec.cluster == "prod-cluster"
    assert rec.resource_group == "rg-prod"
    assert rec.subscription == "sub-1"
    assert rec.admin is False
    assert rec.added_at != ""

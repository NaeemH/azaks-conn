"""Tests for `azaks_conn.config`."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from azaks_conn.config import AliasRecord, load, now_iso, remove, save, state_file, upsert
from azaks_conn.errors import KubeconfigWriteError


def test_state_file_under_home(kube_home: Path) -> None:
    assert state_file() == kube_home / ".kube" / "azaks-conn" / ".aliases.json"


def test_load_missing_returns_empty(kube_home: Path) -> None:
    assert load() == {}


def test_load_empty_file_returns_empty(kube_home: Path) -> None:
    state_file().parent.mkdir(parents=True, exist_ok=True)
    state_file().write_text("")
    assert load() == {}


def test_round_trip(kube_home: Path) -> None:
    rec_a = AliasRecord(
        cluster="cluster-a",
        resource_group="rg-a",
        subscription="sub-1",
        admin=False,
        added_at="2026-06-23T10:00:00Z",
    )
    rec_b = AliasRecord(
        cluster="cluster-b",
        resource_group=None,
        subscription="sub-2",
        admin=True,
        added_at="2026-06-23T11:00:00Z",
    )
    save({"a": rec_a, "b": rec_b})

    loaded = load()
    assert loaded == {"a": rec_a, "b": rec_b}


def test_save_chmod_600(kube_home: Path) -> None:
    save({"x": AliasRecord(cluster="c", added_at="t")})
    perms = stat.S_IMODE(state_file().stat().st_mode)
    assert perms == 0o600


def test_save_chmod_dir_700(kube_home: Path) -> None:
    save({"x": AliasRecord(cluster="c", added_at="t")})
    dir_perms = stat.S_IMODE(state_file().parent.stat().st_mode)
    assert dir_perms == 0o700


def test_save_tightens_preexisting_loose_dir(kube_home: Path) -> None:
    """A pre-existing world-readable state dir is tightened to 0700 on save."""
    d = state_file().parent
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o777)
    save({"x": AliasRecord(cluster="c", added_at="t")})
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


def test_save_contents_are_sorted_json(kube_home: Path) -> None:
    save(
        {
            "b": AliasRecord(cluster="cb"),
            "a": AliasRecord(cluster="ca"),
        }
    )
    raw = state_file().read_text()
    parsed = json.loads(raw)
    assert list(parsed["aliases"].keys()) == ["a", "b"]


def test_load_rejects_garbage(kube_home: Path) -> None:
    state_file().parent.mkdir(parents=True, exist_ok=True)
    state_file().write_text('["not", "a", "dict"]')
    with pytest.raises(KubeconfigWriteError, match="not a valid aksc state file"):
        load()


def test_load_rejects_invalid_json(kube_home: Path) -> None:
    state_file().parent.mkdir(parents=True, exist_ok=True)
    state_file().write_text("{not-json")
    with pytest.raises(KubeconfigWriteError, match="failed to read"):
        load()


def test_load_ignores_non_dict_records(kube_home: Path) -> None:
    state_file().parent.mkdir(parents=True, exist_ok=True)
    state_file().write_text(
        json.dumps(
            {
                "aliases": {
                    "good": {"cluster": "c1", "added_at": "t"},
                    "bad": "not-a-dict",
                }
            }
        )
    )
    out = load()
    assert "good" in out
    assert "bad" not in out


def test_upsert_adds_then_replaces(kube_home: Path) -> None:
    upsert("p", AliasRecord(cluster="prod-cluster", added_at="t1"))
    assert load()["p"].cluster == "prod-cluster"
    upsert("p", AliasRecord(cluster="prod-cluster-v2", added_at="t2"))
    assert load()["p"].cluster == "prod-cluster-v2"
    assert load()["p"].added_at == "t2"


def test_remove_returns_true_when_present(kube_home: Path) -> None:
    upsert("p", AliasRecord(cluster="prod-cluster", added_at="t"))
    assert remove("p") is True
    assert load() == {}


def test_remove_returns_false_when_absent(kube_home: Path) -> None:
    assert remove("ghost") is False


def test_save_leaves_no_temp_on_failure(kube_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If json.dump explodes mid-write, no .aliases-*.tmp file is left."""

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr("azaks_conn.config.json.dump", _explode)
    with pytest.raises(RuntimeError, match="disk full"):
        save({"x": AliasRecord(cluster="c", added_at="t")})
    leftovers = list(state_file().parent.glob(".aliases-*.tmp"))
    assert leftovers == [], f"tempfile leaked: {leftovers}"


def test_now_iso_format() -> None:
    ts = now_iso()
    # 2026-06-23T08:30:00Z
    assert len(ts) == 20
    assert ts.endswith("Z")
    assert ts[4] == "-" and ts[7] == "-"
    assert ts[10] == "T"
    assert ts[13] == ":" and ts[16] == ":"

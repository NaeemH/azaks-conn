"""Tests for `azaks_conn.kubectl`."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from azaks_conn.errors import KubectlNotFoundError, KubectlProbeError
from azaks_conn.kubectl import cluster_info


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    raises: type[BaseException] | None = None,
) -> list[list[str]]:
    """Wire shutil.which + subprocess.run for tests. Returns recorded argv list."""
    calls: list[list[str]] = []

    def _which(cmd: str) -> str | None:
        return "/usr/bin/kubectl" if cmd == "kubectl" else None

    def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if raises is not None:
            raise raises("simulated")
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr("azaks_conn.kubectl.shutil.which", _which)
    monkeypatch.setattr("azaks_conn.kubectl.subprocess.run", _run)
    return calls


def test_missing_kubectl_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("azaks_conn.kubectl.shutil.which", lambda _c: None)
    with pytest.raises(KubectlNotFoundError, match="not on PATH"):
        cluster_info("prod")


def test_happy_path_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_subprocess(
        monkeypatch,
        stdout="Kubernetes control plane is running at https://example:443\n",
    )
    out = cluster_info("prod", timeout_seconds=7)
    assert "control plane" in out
    argv = calls[0]
    assert argv[0] == "/usr/bin/kubectl"
    assert argv[1:3] == ["--context", "prod"]
    assert "cluster-info" in argv
    assert "--request-timeout=7s" in argv


def test_non_zero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_subprocess(
        monkeypatch,
        returncode=1,
        stderr="Unable to connect to the server: dial tcp ...",
    )
    with pytest.raises(KubectlProbeError, match="Unable to connect"):
        cluster_info("prod")


def test_stderr_empty_falls_back_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_subprocess(
        monkeypatch,
        returncode=1,
        stderr="",
        stdout="some failure detail on stdout",
    )
    with pytest.raises(KubectlProbeError, match="some failure detail"):
        cluster_info("prod")


def test_timeout_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    def _which(cmd: str) -> str | None:
        return "/usr/bin/kubectl"

    def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr("azaks_conn.kubectl.shutil.which", _which)
    monkeypatch.setattr("azaks_conn.kubectl.subprocess.run", _run)
    with pytest.raises(KubectlProbeError, match="timed out"):
        cluster_info("prod", timeout_seconds=3)

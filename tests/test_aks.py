"""Tests for `azaks_conn.aks.get_credentials`."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from azaks_conn.aks import get_credentials
from azaks_conn.errors import AksAccessError, ClusterNotFoundError


def _make_fake_run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int = 0,
    stderr: str = "",
    file_contents: dict[str, Any] | None = None,
) -> list[list[str]]:
    """Wire shutil.which + subprocess.run to record argv and stub `az`.

    Returns a list that will be appended-to with each subprocess.run argv.
    If `file_contents` is given, the fake `az` writes that YAML to the `-f`/`--file`
    argument before returning.
    """
    calls: list[list[str]] = []

    def _which(cmd: str) -> str | None:
        return "/usr/bin/az" if cmd == "az" else None

    def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        if file_contents is not None:
            # Find -f or --file
            for flag in ("-f", "--file"):
                if flag in argv:
                    path = argv[argv.index(flag) + 1]
                    Path(path).write_text(yaml.safe_dump(file_contents))
                    break
        return subprocess.CompletedProcess(argv, returncode, "", stderr)

    monkeypatch.setattr("azaks_conn.aks.shutil.which", _which)
    monkeypatch.setattr("azaks_conn.aks.subprocess.run", _run)
    return calls


def test_az_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("azaks_conn.aks.shutil.which", lambda _c: None)
    with pytest.raises(AksAccessError, match="not found on PATH"):
        get_credentials("my-cluster")


def test_happy_path_minimal_argv(
    monkeypatch: pytest.MonkeyPatch, az_kubeconfig: dict[str, Any]
) -> None:
    calls = _make_fake_run(monkeypatch, file_contents=az_kubeconfig)
    cfg = get_credentials("my-cluster")
    assert cfg["current-context"] == "my-cluster"
    assert len(calls) == 1
    argv = calls[0]
    assert argv[0] == "/usr/bin/az"
    assert argv[1:3] == ["aks", "get-credentials"]
    assert "--name" in argv and argv[argv.index("--name") + 1] == "my-cluster"
    assert "--file" in argv
    assert "--overwrite-existing" in argv
    # No optional flags
    assert "--resource-group" not in argv
    assert "--subscription" not in argv
    assert "--admin" not in argv


def test_optional_flags_passthrough(
    monkeypatch: pytest.MonkeyPatch, az_kubeconfig: dict[str, Any]
) -> None:
    calls = _make_fake_run(monkeypatch, file_contents=az_kubeconfig)
    get_credentials(
        "my-cluster",
        resource_group="my-rg",
        subscription="sub-123",
        admin=True,
    )
    argv = calls[0]
    assert argv[argv.index("--resource-group") + 1] == "my-rg"
    assert argv[argv.index("--subscription") + 1] == "sub-123"
    assert "--admin" in argv


def test_cluster_not_found_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    _make_fake_run(
        monkeypatch,
        returncode=1,
        stderr="ResourceNotFound: The Resource 'Microsoft.ContainerService/managedClusters/x' was not found.",
    )
    with pytest.raises(ClusterNotFoundError, match="not found"):
        get_credentials("ghost")


def test_generic_az_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _make_fake_run(
        monkeypatch,
        returncode=1,
        stderr="AuthorizationFailed: caller is missing permission",
    )
    with pytest.raises(AksAccessError, match="AuthorizationFailed"):
        get_credentials("my-cluster")
    # And it must NOT be classified as ClusterNotFoundError
    _make_fake_run(
        monkeypatch,
        returncode=1,
        stderr="AuthorizationFailed: caller is missing permission",
    )
    with pytest.raises(AksAccessError) as ei:
        get_credentials("my-cluster")
    assert not isinstance(ei.value, ClusterNotFoundError)


def test_stderr_traceback_is_condensed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A multi-line `az` crash (ERROR lines + Python traceback) is condensed.

    Only the `ERROR:` lines should surface; the traceback noise is dropped.
    """
    stderr = (
        "ERROR: The command failed with an unexpected error. Here is the traceback:\n"
        "ERROR: No module named 'azure.graphrbac'\n"
        "Traceback (most recent call last):\n"
        '  File "/opt/az/lib/python3.13/site-packages/knack/cli.py", line 233, in invoke\n'
        "    cmd_result = self.invocation.execute(args)\n"
    )
    _make_fake_run(monkeypatch, returncode=1, stderr=stderr)
    with pytest.raises(AksAccessError) as ei:
        get_credentials("my-cluster")
    msg = str(ei.value)
    assert "No module named 'azure.graphrbac'" in msg
    assert "Traceback" not in msg
    assert "knack/cli.py" not in msg


def test_bare_not_found_not_misclassified(monkeypatch: pytest.MonkeyPatch) -> None:
    """A generic error mentioning 'not found' (but not an AKS marker) stays generic.

    Regression for the previously over-broad `"not found"` substring heuristic.
    """
    _make_fake_run(
        monkeypatch,
        returncode=1,
        stderr="ERROR: config file not found in cache",
    )
    with pytest.raises(AksAccessError) as ei:
        get_credentials("my-cluster")
    assert not isinstance(ei.value, ClusterNotFoundError)


def test_invalid_yaml_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """If `az` returns 0 but the file is somehow not a dict, fail loud."""
    calls: list[list[str]] = []

    def _which(cmd: str) -> str | None:
        return "/usr/bin/az"

    def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        # Write a scalar instead of a mapping
        for flag in ("-f", "--file"):
            if flag in argv:
                Path(argv[argv.index(flag) + 1]).write_text("just-a-string\n")
                break
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("azaks_conn.aks.shutil.which", _which)
    monkeypatch.setattr("azaks_conn.aks.subprocess.run", _run)
    with pytest.raises(AksAccessError, match="invalid YAML"):
        get_credentials("my-cluster")


def test_tmpfile_is_cleaned_up(
    monkeypatch: pytest.MonkeyPatch, az_kubeconfig: dict[str, Any]
) -> None:
    """The kubeconfig tmpfile passed to `az -f` must be deleted afterwards."""
    captured: dict[str, str] = {}

    def _which(cmd: str) -> str | None:
        return "/usr/bin/az"

    def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        path = argv[argv.index("--file") + 1]
        captured["tmp"] = path
        Path(path).write_text(yaml.safe_dump(az_kubeconfig))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("azaks_conn.aks.shutil.which", _which)
    monkeypatch.setattr("azaks_conn.aks.subprocess.run", _run)
    get_credentials("my-cluster")
    assert "tmp" in captured
    assert not Path(captured["tmp"]).exists(), "tmpfile leaked"

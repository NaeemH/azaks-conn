"""Shared pytest fixtures for azaks-conn."""

from __future__ import annotations

# Add shared fixtures here as the test surface grows.
# Common patterns from the rest of the series:
#
# @pytest.fixture
# def fake_az(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
#     """Stub shutil.which("az") + subprocess.run; record argv lists."""
#     calls: list[list[str]] = []
#
#     def _which(cmd: str) -> str | None:
#         return "/usr/bin/az" if cmd == "az" else None
#
#     def _run(argv, **kwargs):
#         calls.append(list(argv))
#         return subprocess.CompletedProcess(argv, 0, "", "")
#
#     monkeypatch.setattr("shutil.which", _which)
#     monkeypatch.setattr("subprocess.run", _run)
#     return calls

"""Shell out to `az aks get-credentials` and return the parsed kubeconfig dict.

We intentionally do **not** pull in any Azure management SDK here — the `az`
CLI already handles authentication, MSAL caching, AAD/AKS RBAC, and emits a
ready-to-use kubeconfig YAML. Shelling out keeps this tool small, predictable,
and aligned with whatever az version the operator already runs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

import yaml

from azaks_conn.errors import AksAccessError, ClusterNotFoundError


def get_credentials(
    cluster: str,
    *,
    resource_group: str | None = None,
    subscription: str | None = None,
    admin: bool = False,
) -> dict[str, Any]:
    """Invoke `az aks get-credentials -n <cluster> -f <tmp>` and return its YAML.

    Args:
        cluster: AKS cluster name.
        resource_group: Optional `-g` value; if omitted, `az` resolves it from
            its own state (subscription default + cluster name uniqueness).
        subscription: Optional `--subscription` value.
        admin: Pass `--admin` for cluster-admin (non-AAD) credentials.

    Raises:
        AksAccessError: `az` not on PATH, or the invocation failed.
        ClusterNotFoundError: stderr from `az` indicates the cluster is missing.
    """
    az = shutil.which("az")
    if az is None:
        raise AksAccessError("`az` CLI not found on PATH. Install Azure CLI: https://aka.ms/azcli")

    fd, tmp_str = tempfile.mkstemp(prefix="azaks-conn-", suffix=".kubeconfig")
    os.close(fd)
    tmp = Path(tmp_str)
    try:
        argv: list[str] = [
            az,
            "aks",
            "get-credentials",
            "--name",
            cluster,
            "--file",
            str(tmp),
            "--overwrite-existing",
            "--only-show-errors",
        ]
        if resource_group:
            argv += ["--resource-group", resource_group]
        if subscription:
            argv += ["--subscription", subscription]
        if admin:
            argv += ["--admin"]

        result = subprocess.run(argv, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stderr_lower = stderr.lower()
            if (
                "resourcenotfound" in stderr_lower
                or "could not be found" in stderr_lower
                or "was not found" in stderr_lower
                or "not found" in stderr_lower
            ):
                raise ClusterNotFoundError(
                    f"AKS cluster {cluster!r} not found: {stderr or '(no detail)'}"
                )
            raise AksAccessError(
                f"`az aks get-credentials` failed (exit {result.returncode}): "
                f"{stderr or '(no stderr)'}"
            )

        try:
            cfg = yaml.safe_load(tmp.read_text())
        except (OSError, yaml.YAMLError) as exc:
            raise AksAccessError(f"failed to parse kubeconfig from `az`: {exc}") from exc
        if not isinstance(cfg, dict):
            raise AksAccessError("`az aks get-credentials` produced invalid YAML")
        return cast(dict[str, Any], cfg)
    finally:
        tmp.unlink(missing_ok=True)

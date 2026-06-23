"""Shell out to `kubectl` for connectivity probes.

Kept separate from `aks.py` so the dependency graph is explicit: aks.py owns
the `az` shell-out (fetch credentials), kubectl.py owns the `kubectl` shell-out
(verify reachability). Both follow the same fail-closed pattern: missing
binary -> NotFoundError; non-zero exit -> ProbeError with the captured stderr.
"""

from __future__ import annotations

import shutil
import subprocess

from azaks_conn.errors import KubectlNotFoundError, KubectlProbeError

DEFAULT_TIMEOUT_SECONDS = 10


def cluster_info(context: str, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Run `kubectl --context CTX cluster-info --request-timeout=Ns`.

    `cluster-info` is the canonical "am I connected to this cluster?" probe —
    it hits `/api` discovery and prints the control-plane endpoint, requiring
    no app-level RBAC beyond the public discovery surface.

    Returns:
        kubectl stdout on success.

    Raises:
        KubectlNotFoundError: `kubectl` is not on PATH.
        KubectlProbeError: kubectl exited non-zero (network failure, expired
            token, deleted cluster, etc.) or timed out.
    """
    kubectl = shutil.which("kubectl")
    if kubectl is None:
        raise KubectlNotFoundError(
            "`kubectl` not on PATH. Install: https://kubernetes.io/docs/tasks/tools/"
        )

    argv = [
        kubectl,
        "--context",
        context,
        "cluster-info",
        f"--request-timeout={timeout_seconds}s",
    ]
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds + 5,
        )
    except subprocess.TimeoutExpired as exc:
        raise KubectlProbeError(
            f"kubectl probe timed out after {timeout_seconds}s for context {context!r}"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise KubectlProbeError(
            f"kubectl probe failed for context {context!r} "
            f"(exit {result.returncode}): {detail or '(no output)'}"
        )
    return result.stdout

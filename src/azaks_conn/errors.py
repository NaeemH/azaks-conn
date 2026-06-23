"""Typed errors raised by the package."""

from __future__ import annotations


class AzaksConnError(Exception):
    """Base class for all package errors."""


class AksAccessError(AzaksConnError):
    """Raised when `az aks ...` cannot be invoked or returns an error."""


class ClusterNotFoundError(AksAccessError):
    """Raised when the named AKS cluster does not exist (or caller lacks RBAC)."""


class KubeconfigWriteError(AzaksConnError):
    """Raised when a kubeconfig file cannot be read, parsed, or written safely."""


class KubectlNotFoundError(AzaksConnError):
    """Raised when `kubectl` is not on PATH."""


class KubectlProbeError(AzaksConnError):
    """Raised when a kubectl probe (cluster-info etc.) exits non-zero."""


class UnknownAliasError(AzaksConnError):
    """Raised when the operator references an alias aksc does not manage."""

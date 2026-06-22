"""Typed errors raised by the package."""

from __future__ import annotations


class AzaksConnError(Exception):
    """Base class for all package errors."""


# TODO: add tool-specific subclasses, e.g.
#
# class AksAccessError(AzaksConnError):
#     """Raised when the AKS API is unreachable or caller lacks permission."""
#
# class KubeconfigWriteError(AzaksConnError):
#     """Raised when ~/.kube/config cannot be written safely."""

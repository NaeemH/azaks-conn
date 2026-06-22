"""Typed errors raised by the package."""

from __future__ import annotations


class __CLI_NAME_CAMEL__Error(Exception):
    """Base class for all package errors."""


# TODO: add tool-specific subclasses, e.g.
#
# class AksAccessError(__CLI_NAME_CAMEL__Error):
#     """Raised when the AKS API is unreachable or caller lacks permission."""
#
# class KubeconfigWriteError(__CLI_NAME_CAMEL__Error):
#     """Raised when ~/.kube/config cannot be written safely."""

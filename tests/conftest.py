"""Shared pytest fixtures for azaks-conn."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def az_kubeconfig() -> dict[str, Any]:
    """A minimal kubeconfig matching what `az aks get-credentials -n X` emits."""
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "preferences": {},
        "clusters": [
            {
                "name": "my-cluster",
                "cluster": {
                    "server": "https://my-cluster.example.azmk8s.io:443",
                    "certificate-authority-data": "FAKE_CA",
                },
            }
        ],
        "users": [
            {
                "name": "clusterUser_my-rg_my-cluster",
                "user": {
                    "exec": {
                        "apiVersion": "client.authentication.k8s.io/v1beta1",
                        "command": "kubelogin",
                        "args": ["get-token", "--login", "devicecode"],
                    }
                },
            }
        ],
        "contexts": [
            {
                "name": "my-cluster",
                "context": {
                    "cluster": "my-cluster",
                    "user": "clusterUser_my-rg_my-cluster",
                },
            }
        ],
        "current-context": "my-cluster",
    }


@pytest.fixture
def kube_home(tmp_path, monkeypatch):
    """Redirect ~/.kube to a per-test tmp dir via $HOME."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path

# azaks-conn

Fetch AKS kubeconfig and merge into ~/.kube/config by alias

## Install

```bash
pip install azaks-conn
```

The package installs two console scripts that point at the same Typer app:

| Command         | Use when                              |
| --------------- | ------------------------------------- |
| `azaks-conn`  | Long form, friendly for scripts       |
| `aksc` | Short alias for interactive shell use |

> Installing with `pipx` drops the scripts in `~/.local/bin`. If that directory
> isn't on your `PATH`, run `pipx ensurepath` and restart your shell. `aksc`
> prints a one-line reminder to stderr if it detects this situation.

## Usage

```bash
aksc --help
aksc --version
```

Four commands cover the alias lifecycle:

| Command | Purpose |
| --- | --- |
| `aksc connect CLUSTER [--alias NAME] [--resource-group RG] [--subscription SUB] [--admin] [--overwrite]` | Fetch AKS credentials and merge into `~/.kube/config` under the given alias. |
| `aksc refresh ALIAS` | Re-fetch credentials for an existing alias using its recorded cluster / RG / subscription / admin flag. Useful after CA rotation or kubelogin cache expiry. |
| `aksc list` | Rich-table inventory of aksc-managed aliases (with provenance metadata). Add `--json` for machine-readable output, or `--no-truncate` to keep full column values (auto-enabled when piped). |
| `aksc verify ALIAS [--timeout N]` | Probe the alias's API server via `kubectl cluster-info`. |
| `aksc rm ALIAS [--force]` | Remove the alias from `~/.kube/config`, the snapshot directory, and the state file. |

State lives in two places under `~/.kube/azaks-conn/`:

- `<alias>` — a single-context kubeconfig snapshot for each managed alias (mode `0600`).
- `.aliases.json` — JSON metadata (cluster, RG, subscription, admin flag, timestamp), used by `list` and `verify`.

## Security model

`aksc connect` shells out to `az aks get-credentials`. By default this fetches
an **Entra ID (AAD) integrated** kubeconfig: actual authentication still flows
through `kubelogin` and your Azure identity, and cluster RBAC applies.

The `--admin` flag passes through to `az aks get-credentials --admin`, which
returns a **cluster-admin certificate** in the kubeconfig. This bypasses Entra
ID and RBAC entirely — anyone with the file is cluster-admin until the
certificate expires (typically months).

`aksc` makes admin contexts visually obvious so they aren't accidentally
shared, committed, or left lying around:

- `aksc connect --admin` prints a yellow `warning:` line citing the bypass.
- `aksc list` flags the alias with a red `ADMIN` marker in the Admin column.
- `aksc verify <admin-alias>` reprints the warning after each probe.
- Both the merged entry in `~/.kube/config` and the per-alias snapshot under
  `~/.kube/azaks-conn/` are written with mode `0600`.

Guidance:

- Prefer the default (AAD) flow whenever possible.
- Only use `--admin` for cluster bootstrap / break-glass work.
- Treat any `--admin` kubeconfig as a high-privilege secret — do not check it
  into source control, share it over chat, or copy it to shared hosts.
- `aksc rm <admin-alias>` is the fastest way to revoke local access; for full
  revocation, rotate the cluster admin credentials in Azure.

## Development

```bash
git clone https://github.com/NaeemH/azaks-conn.git
cd azaks-conn
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

# Run the standard checks
ruff check . && ruff format --check .
mypy src
pytest -q
```

## Release

Releases are tag-driven. Bump `src/azaks_conn/__about__.py`, commit, then:

```bash
git tag v0.3.1
git push origin v0.3.1
```

`.github/workflows/release.yml` builds the sdist + wheel and publishes to PyPI
via Trusted Publishers (OIDC) — no API tokens involved.

## License

[MIT](LICENSE)

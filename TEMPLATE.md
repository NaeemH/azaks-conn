# azops-cli-template

GitHub template repo for the **NaeemH/azops** family of Azure-operator CLI
tools — a consistent scaffold so each new tool starts with the same shape:

- Python 3.10+, `src/` layout, `hatchling` build backend
- **Dynamic version** sourced from `src/<pkg>/__about__.py` (single source of
  truth — no `version =` in `pyproject.toml` to drift out of sync)
- `typer` + `rich` CLI surface with `--version` and `--help` already wired
- `ruff` (lint+format) and `mypy --strict` on `src/`
- `pytest` + `pytest-cov` + `pytest-mock` with placeholders for `pytest-recording` / `vcrpy`
- GitHub Actions matrix CI (3.10/3.11/3.12) + tag-driven release to PyPI via
  Trusted Publishers (OIDC, no API tokens)
- Pre-commit hooks (ruff, mypy, yaml/toml/whitespace)
- MIT license

Sibling tools built from this scaffold:

- [`azkv-ssh-fetch`](https://github.com/NaeemH/azkv-ssh-fetch) — fetch SSH keys from Azure Key Vault
- [`avnm-pool-cidr`](https://github.com/NaeemH/avnm-pool-cidr) — pick next CIDR from an AVNM IPAM pool

## Use this template

### On GitHub

1. Click **Use this template → Create a new repository** on the GitHub page.
2. Name it after your tool's kebab-case CLI name (e.g. `azaks-conn`).
3. `git clone` the new repo locally.
4. Run the bootstrap script (see below).

### Bootstrap

The template ships with literal `__PKG_NAME__` / `__CLI_NAME__` / `__CLI_ALIAS__`
/ `__DESCRIPTION__` / `__YEAR__` / `__CLI_NAME_CAMEL__` / `__PKG_NAME_UPPER__`
placeholders. The bootstrap script substitutes them all and renames the
`src/__PKG_NAME__/` directory:

```bash
./scripts/bootstrap.sh
# interactive — will prompt for the 4 values
```

Or pass arguments directly:

```bash
./scripts/bootstrap.sh \
  --pkg azaks_conn \
  --cli azaks-conn \
  --alias aksc \
  --desc "Fetch AKS kubeconfig and merge into ~/.kube/config by alias"
```

After it finishes, the script deletes itself and this `TEMPLATE.md` file, then
prints next-step instructions.

## Placeholder reference

| Placeholder              | Example value for `azaks-conn`                       | Where used                                                 |
| ------------------------ | ---------------------------------------------------- | ---------------------------------------------------------- |
| `__PKG_NAME__`           | `azaks_conn`                                         | Python package dir name + imports                          |
| `__CLI_NAME__`           | `azaks-conn`                                         | PyPI dist name + long-form console script                  |
| `__CLI_ALIAS__`          | `aksc`                                               | Short console-script alias                                 |
| `__DESCRIPTION__`        | "Fetch AKS kubeconfig and merge into ~/.kube/config" | `pyproject.toml`, `__init__.py` docstring, README          |
| `__YEAR__`               | `2026`                                               | `LICENSE` copyright year                                   |
| `__CLI_NAME_CAMEL__`     | `AzaksConn`                                          | Base exception class name in `errors.py`                   |
| `__PKG_NAME_UPPER__`     | `AZAKS_CONN`                                         | Debug env-var prefix in `__main__.py`                      |

The last two are derived automatically by the bootstrap script from the first
two — you don't enter them.

## After bootstrap

```bash
git init  # if cloning, this is already done
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

# Verify the scaffold is healthy
ruff check . && ruff format --check .
mypy src
pytest -q
```

Then start replacing the placeholder `hello` command in `src/<pkg>/cli.py`
with real subcommands. See the sibling repos for full examples.

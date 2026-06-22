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

## Usage

```bash
aksc --help
aksc --version
```

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
git tag v0.1.0
git push origin v0.1.0
```

`.github/workflows/release.yml` builds the sdist + wheel and publishes to PyPI
via Trusted Publishers (OIDC) — no API tokens involved.

## License

[MIT](LICENSE)

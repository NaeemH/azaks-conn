# __CLI_NAME__

__DESCRIPTION__

## Install

```bash
pip install __CLI_NAME__
```

The package installs two console scripts that point at the same Typer app:

| Command         | Use when                              |
| --------------- | ------------------------------------- |
| `__CLI_NAME__`  | Long form, friendly for scripts       |
| `__CLI_ALIAS__` | Short alias for interactive shell use |

## Usage

```bash
__CLI_ALIAS__ --help
__CLI_ALIAS__ --version
```

## Development

```bash
git clone https://github.com/NaeemH/__CLI_NAME__.git
cd __CLI_NAME__
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

# Run the standard checks
ruff check . && ruff format --check .
mypy src
pytest -q
```

## Release

Releases are tag-driven. Bump `src/__PKG_NAME__/__about__.py`, commit, then:

```bash
git tag v0.1.0
git push origin v0.1.0
```

`.github/workflows/release.yml` builds the sdist + wheel and publishes to PyPI
via Trusted Publishers (OIDC) — no API tokens involved.

## License

[MIT](LICENSE)

#!/usr/bin/env bash
# bootstrap.sh — substitute placeholders + rename package dir, then self-destruct.
#
# Usage:
#   ./scripts/bootstrap.sh                              # interactive prompts
#   ./scripts/bootstrap.sh --pkg X --cli Y --alias Z --desc "..."
#
# Placeholders substituted across every tracked text file:
#   __PKG_NAME__        e.g. azaks_conn       (snake_case)
#   __CLI_NAME__        e.g. azaks-conn       (kebab-case, PyPI name)
#   __CLI_ALIAS__       e.g. aksc             (short console-script alias)
#   __DESCRIPTION__     free text
#   __YEAR__            current year, auto
#   __CLI_NAME_CAMEL__  derived: PascalCase of PKG_NAME (AzaksConn)
#   __PKG_NAME_UPPER__  derived: UPPER_SNAKE of PKG_NAME (AZAKS_CONN)
#
# Requires GNU sed. On macOS install via `brew install gnu-sed` and re-run
# with `PATH="/opt/homebrew/opt/gnu-sed/libexec/gnubin:$PATH"`.

set -euo pipefail

die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m==>\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------- args ----
pkg=""
cli=""
alias_=""
desc=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pkg)    pkg="$2";    shift 2 ;;
    --cli)    cli="$2";    shift 2 ;;
    --alias)  alias_="$2"; shift 2 ;;
    --desc)   desc="$2";   shift 2 ;;
    -h|--help)
      sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "unknown arg: $1" ;;
  esac
done

prompt_if_empty() {
  local varname="$1" message="$2" example="$3" current
  current="${!varname}"
  if [[ -z "$current" ]]; then
    read -r -p "$message [$example]: " current
    printf -v "$varname" '%s' "$current"
  fi
}

prompt_if_empty pkg    "Python package name (snake_case)"  "azaks_conn"
prompt_if_empty cli    "CLI / PyPI name (kebab-case)"      "azaks-conn"
prompt_if_empty alias_ "Short alias (no separators)"       "aksc"
prompt_if_empty desc   "One-line description"              "Fetch AKS kubeconfig and merge into ~/.kube/config by alias"

# ------------------------------------------------------------ validate ----
[[ "$pkg"    =~ ^[a-z][a-z0-9_]*$           ]] || die "PKG must be snake_case ([a-z][a-z0-9_]*): got '$pkg'"
[[ "$cli"    =~ ^[a-z][a-z0-9-]*[a-z0-9]$   ]] || die "CLI must be kebab-case ([a-z][a-z0-9-]*[a-z0-9]): got '$cli'"
[[ "$alias_" =~ ^[a-z][a-z0-9]*$            ]] || die "ALIAS must be lowercase letters/digits, no separators: got '$alias_'"
[[ -n "$desc" ]] || die "DESCRIPTION cannot be empty"

# ------------------------------------------------------------- derive ----
year="$(date +%Y)"
pkg_upper="$(printf '%s' "$pkg" | tr '[:lower:]' '[:upper:]')"
cli_camel="$(printf '%s' "$pkg" | awk -F_ '{for(i=1;i<=NF;i++)$i=toupper(substr($i,1,1))substr($i,2)}1' OFS='')"

cat <<EOF

Bootstrap plan
  __PKG_NAME__        -> $pkg
  __CLI_NAME__        -> $cli
  __CLI_ALIAS__       -> $alias_
  __DESCRIPTION__     -> $desc
  __YEAR__            -> $year (auto)
  __CLI_NAME_CAMEL__  -> $cli_camel (derived)
  __PKG_NAME_UPPER__  -> $pkg_upper (derived)

EOF

read -r -p "Proceed? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || die "aborted"

# ------------------------------------------------------ run from root ----
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# Build the list of files to substitute: everything tracked-text-ish,
# excluding the bootstrap script itself and TEMPLATE.md (both will be deleted).
mapfile -t files < <(
  find . -type f \
    -not -path './.git/*' \
    -not -path './scripts/bootstrap.sh' \
    -not -path './TEMPLATE.md' \
    -not -path './.venv/*' \
    -not -name '*.pyc'
)

info "Substituting placeholders in ${#files[@]} files..."

# Escape any sed-special chars in $desc (only / and & matter for the
# right-hand side of s///).
sed_escape() { printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'; }
desc_esc="$(sed_escape "$desc")"

# Order matters: substitute the longer, more-specific placeholders first so
# we don't half-substitute __PKG_NAME_UPPER__ when replacing __PKG_NAME__.
for f in "${files[@]}"; do
  sed -i \
    -e "s/__CLI_NAME_CAMEL__/$cli_camel/g" \
    -e "s/__PKG_NAME_UPPER__/$pkg_upper/g" \
    -e "s/__CLI_NAME__/$cli/g" \
    -e "s/__CLI_ALIAS__/$alias_/g" \
    -e "s/__PKG_NAME__/$pkg/g" \
    -e "s/__DESCRIPTION__/$desc_esc/g" \
    -e "s/__YEAR__/$year/g" \
    "$f"
done

# ---------------------------------------------------------- rename dir ----
info "Renaming src/__PKG_NAME__/ -> src/$pkg/"
mv "src/__PKG_NAME__" "src/$pkg"

# ------------------------------------------------------ self-destruct ----
info "Deleting TEMPLATE.md and scripts/bootstrap.sh"
rm -f TEMPLATE.md
# rmdir scripts/ if empty (it should be)
rm -f scripts/bootstrap.sh
rmdir scripts 2>/dev/null || true

printf '\n\033[32mDone!\033[0m Next steps:\n\n'
cat <<EOF
  python -m venv .venv && source .venv/bin/activate
  pip install -e ".[dev]"
  pre-commit install

  ruff check . && ruff format --check .
  mypy src
  pytest -q

Then start replacing the placeholder \`hello\` command in
\`src/$pkg/cli.py\` with real subcommands.

Suggested first commit:

  git add -A
  git commit -m "Initial scaffold from azops-cli-template"

EOF

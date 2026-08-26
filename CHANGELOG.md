# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Track GitHub Actions and Python dependencies with Dependabot. (#15)

## [0.3.2] - 2026-06-26

### Added

- `aksc list --json`, and drop the ellipsis truncation when output is piped
  rather than shown on a terminal. (#13)
- Hint at `pipx ensurepath` when `~/.local/bin` is not on PATH, which
  otherwise left the installed console script silently unreachable. (#12)

## [0.3.1] - 2026-06-25

### Fixed

- Condense `az` error output to the useful lines instead of the full trace,
  and tighten the state directory permissions. (#10)

## [0.3.0] - 2026-06-23

### Added

- `aksc refresh`, re-fetching credentials for an existing alias. (#4)
- `--admin` UX polish, and a documented security model in the README. (#3)

## [0.2.0] - 2026-06-22

### Added

- `list`, `verify` and `rm`, backed by an alias state file. (#2)

## [0.1.0] - 2026-06-22

### Added

- Initial release: fetch AKS credentials and merge them into kubeconfig. (#1)

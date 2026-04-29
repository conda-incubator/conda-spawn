# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-04-29

### Added

- Best-effort support for `fish`, `csh`/`tcsh`, and `xonsh` shells
  ([#21], [#28]).
- New `conda_spawn.contrib` module for shell registration discovery and
  `conda_spawn.registry` module for the in-process shell registry.
- Public subclass extension hooks on `Shell`/`UnixShell` (the leading
  underscores were dropped) so out-of-tree plugins can extend behaviour
  without reaching into private API.
- Non-PTY unit tests for `UnixShell` alongside the existing PTY-based
  integration tests.
- Dependabot configuration for GitHub Actions, pre-commit, and pip.

### Changed

- Renamed `UnixTTYShell` to `UnixShell`.
- Modernized the supported Python versions to 3.10–3.14 and the matching
  CI matrix.
- CI now tests against `conda-forge` only; the `defaults` channel was
  dropped from the matrix.
- Tests were split to mirror the module layout (`shell` / `contrib` /
  `registry`) and parameterized with shared fixtures.

### Fixed

- Double shell prompt when spawning a new shell ([#22]).
- PowerShell `-NoExit` is now skipped when stdin is not a TTY ([#30]).
- `$CONDA_ROOT/condabin` stays first in `PATH` when replacing a prefix.
- Ready-marker synchronization is sourced from the activation script to
  avoid PTY echo leaks.

### Removed

- `spawn -n` / `spawn -p` mentions left over in the documentation.

## [0.0.5] - 2025-01-29

- Removed `-n, --name` and `-p, --prefix` flags in favour of a positional
  argument, mirroring `conda activate` ([#12]).

## [0.0.4] - 2025-01-20

- Prevent nested activation by default; opt in via `--replace` and
  `--stack` ([#6]).

## [0.0.3] - 2025-01-16

- Avoid `conda` in the base env getting shadowed by other `conda`
  executables on `PATH` ([#5]).

## [0.0.2] - 2025-01-15

- Added the `--hook` option ([#2]).
- Added the initial documentation site ([#3]).

## [0.0.1] - 2025-01-14

- Prototype release.

[0.1.0]: https://github.com/conda-incubator/conda-spawn/compare/0.0.5...0.1.0
[0.0.5]: https://github.com/conda-incubator/conda-spawn/compare/0.0.4...0.0.5
[0.0.4]: https://github.com/conda-incubator/conda-spawn/compare/0.0.3...0.0.4
[0.0.3]: https://github.com/conda-incubator/conda-spawn/compare/0.0.2...0.0.3
[0.0.2]: https://github.com/conda-incubator/conda-spawn/compare/0.0.1...0.0.2
[0.0.1]: https://github.com/conda-incubator/conda-spawn/releases/tag/0.0.1

[#2]: https://github.com/conda-incubator/conda-spawn/pull/2
[#3]: https://github.com/conda-incubator/conda-spawn/pull/3
[#5]: https://github.com/conda-incubator/conda-spawn/pull/5
[#6]: https://github.com/conda-incubator/conda-spawn/pull/6
[#12]: https://github.com/conda-incubator/conda-spawn/pull/12
[#21]: https://github.com/conda-incubator/conda-spawn/issues/21
[#22]: https://github.com/conda-incubator/conda-spawn/pull/22
[#28]: https://github.com/conda-incubator/conda-spawn/pull/28
[#30]: https://github.com/conda-incubator/conda-spawn/pull/30

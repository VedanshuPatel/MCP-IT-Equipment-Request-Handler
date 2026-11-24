# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Project scaffolding: `pyproject.toml` with a `src/` layout and `dev` extras.
- ruff for linting and formatting, with Google-style docstring rules.
- pytest with a branch-coverage gate at 85%.
- GitHub Actions CI: lint, format check and tests on Python 3.12 and 3.15.
- `it_equipment` package skeleton that reads its version from the installed package metadata, with smoke tests.
- Documentation: README, `docs/ARCHITECTURE.md`, this changelog, and the `.env.example` configuration template.

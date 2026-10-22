# Repository Agent Guidelines

This repository provides the `standardize-agent-workspace` skill and Python engine for standardizing AI coding agent configurations across Claude Code, OpenAI Codex, and Antigravity.

## Engineering Standards

- **Language & Runtime**: Pure Python 3.10+ standard library. Zero external PyPI dependencies for the core standardization engine.
- **Testing**: Run all unit tests with `python3 -m unittest discover tests`. All changes must maintain 100% test pass rate.
- **Cross-Platform**: Support POSIX (macOS, Linux, WSL2) natively and include graceful fallbacks for native Windows (`os.name == 'nt'`).
- **Idempotency**: All standardization operations must be strictly idempotent. Running the tool twice against a workspace must yield 0 changes on the second execution.

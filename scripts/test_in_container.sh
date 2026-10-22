#!/usr/bin/env bash
# Runs the standardize-agent-workspace test suite inside an isolated container
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DOCKER_CMD=""
if command -v docker >/dev/null 2>&1; then
  DOCKER_CMD="docker"
elif command -v podman >/dev/null 2>&1; then
  DOCKER_CMD="podman"
else
  echo "Error: Neither docker nor podman found in PATH." >&2
  exit 1
fi

echo "Running test suite inside container using ${DOCKER_CMD} (python:3.12-slim)..."
"${DOCKER_CMD}" run --rm \
  -v "${SKILL_DIR}:/workspace:ro" \
  -w /workspace \
  python:3.12-slim \
  python3 -m unittest discover -s tests -p "test_*.py" -v

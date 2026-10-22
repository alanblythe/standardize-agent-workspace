#!/usr/bin/env bash
# Symlinks standardize-agent-workspace into ~/.gemini/config/skills/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TARGET_DIR="${HOME}/.gemini/config/skills"

mkdir -p "${TARGET_DIR}"
ln -sfn "${SKILL_DIR}" "${TARGET_DIR}/standardize-agent-workspace"

echo "Installed standardize-agent-workspace skill -> ${TARGET_DIR}/standardize-agent-workspace"

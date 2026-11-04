#!/usr/bin/env bash
# Installs the pinned ESLint stack and ruff for the clean-code check; prints the directory to put on PATH.
set -euo pipefail
tool_directory=$(cd "$(dirname "$0")" && pwd)
environment=${1:?usage: install.sh <virtualenv directory>}
npm ci --prefix "$tool_directory" --ignore-scripts --no-audit --no-fund --silent
python3 -m venv "$environment"
"$environment/bin/pip" install --quiet --disable-pip-version-check --require-hashes -r "$tool_directory/requirements.txt"
echo "$environment/bin"

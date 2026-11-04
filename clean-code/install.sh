#!/usr/bin/env bash
# Installs the pinned ESLint stack and ruff for the clean-code check; prints the directory to put on PATH.
# Runs from the tool's own directory with python3 -I, so files in the checked repository cannot shadow
# modules (a venv.py there) or supply npm configuration.
set -euo pipefail
environment=${1:?usage: install.sh <virtualenv directory>}
cd "$(dirname "$0")"
npm ci --ignore-scripts --no-audit --no-fund --silent
python3 -I -m venv "$environment"
"$environment/bin/python" -I -m pip install --quiet --disable-pip-version-check --require-hashes -r requirements.txt
echo "$environment/bin"

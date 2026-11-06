#!/usr/bin/env bash
set -euo pipefail

candidate_repository=${1:?candidate repository directory required}
remote_url=${2:?remote URL required}
commit_sha=${3:?commit SHA required}
[[ "$commit_sha" =~ ^[[:xdigit:]]{40}$ ]]
export GIT_ASKPASS="$(cd "$(dirname "$0")" && pwd)/git-credentials.sh"
export GIT_TERMINAL_PROMPT=0
git init --bare --quiet "$candidate_repository"
git -C "$candidate_repository" remote add origin "$remote_url"
git -C "$candidate_repository" config remote.origin.promisor true
git -C "$candidate_repository" config remote.origin.partialclonefilter blob:none
git -C "$candidate_repository" -c credential.helper= fetch --quiet --no-tags \
  --depth=2 --filter=blob:none origin "$commit_sha"
[[ "$(git -C "$candidate_repository" rev-parse FETCH_HEAD)" == "$commit_sha" ]]
git -C "$candidate_repository" -c credential.helper= cat-file -e FETCH_HEAD^1:.github/hygiene.json

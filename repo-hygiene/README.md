# Repository hygiene

The reusable workflow checks added paths and protects files owned by trunk/release automation. The added-path rule permits modifying or deleting existing files. A rename into a forbidden location counts as an addition. Candidate Git trees are fetched into a bare repository; candidate code and working-tree files are never executed or checked out.

Ordinary PR additions, modifications, deletions or renames of `llms*.txt`, `CHANGELOG.md`, `samples/dist/**`, `docs/bundle-sizes.md` or `api-report/**` are rejected. Release Please changelog changes are allowed only when the trusted PR event identifies a recognized bot as both author and sender, both branches belong to the same repository, the head uses the Release Please branch convention for its base, and the event head SHA matches the fetched merge tree. The recognized identities are `honua-io-bot[bot]` and `github-actions[bot]`, checked by numeric user ID and Bot type. This exception covers only `CHANGELOG.md` files; other ownership and added-path rules still apply. Local checks without `--event` retain all ownership restrictions. Terraform backend blocks in changed `.tf` files must keep the same tokenized content; comments, whitespace and changes outside backend blocks are allowed. Backend additions and deletions are rejected too. Gate-input exceptions cannot bypass these ownership checks. File contents are read from Git objects without executing candidate code.

Each repository owns `.github/hygiene.json`, read with `git show` from the trusted base revision, never from the candidate. The shared repository contains no repository-specific data. Land the configuration before introducing the caller. Policy changes take effect on subsequent pull requests after they land.

```json
{
  "roots": [".github/", ".gitignore", "AGENTS.md", "README.md", "src/", "tests/", "docs/", "scripts/", "eng/"],
  "gate_inputs": {"eng/release/audit.v1.json": "Versioned release-gate input"}
}
```

Root files match exactly; directory entries end with `/`. `gate_inputs` permits exact paths with a reason naming their build or release consumer. For a gate that consumes dynamically named files, `gate_input_directories` maps literal directory prefixes ending in `/` to consumer-specific reasons. These prefixes match descendants only, and cannot bypass root restrictions, scratch paths, backups or other reserved output directories such as `test-results/`. A nested `artifacts/` directory is allowed only beneath an explicit gate-input prefix; the prefix itself cannot contain a reserved output directory. Wildcards are rejected. Keep exceptions short. Source modules and recognized GitHub automation are maintained files. Historical evidence, audits, archives, reports, dated output, scratch directories and backups are rejected. Tools write output beneath gitignored `/artifacts/`; force-adding output there is rejected too. Product repositories cannot add `samples/` except beneath a named gate-input directory; exact file exceptions do not bypass that restriction. A sample repository can set `"samples": true` in its own configuration.

Callers run on every `pull_request`, with no path filter, using an immutable commit:

```yaml
name: Repository hygiene
on:
  pull_request:
    types: [opened, synchronize, reopened, edited]
permissions:
  contents: read
jobs:
  repo-hygiene:
    uses: honua-io/.github/.github/workflows/repo-hygiene.yml@<sha>
```

The required check context is `repo-hygiene / Repository hygiene`. The workflow supports GitHub.com pull-request events; it does not support merge queues or `pull_request_target`. Missing or malformed base policy fails closed. Configure the required check only after the caller has passed on a real PR.

Run locally from the target repository with the shared tool's absolute path:

```sh
python3 -I /path/to/shared/repo-hygiene/check.py --base origin/trunk
```

Test the tool from the shared repository:

```sh
python3 -m unittest discover -s repo-hygiene -p 'test_*.py'
```

## Runner environment

The reusable workflow uses `HONUA_LIGHT_RUNNER` for same-repository pull requests and falls back to `ubuntu-latest` for forks or an unset variable. Its first step exports `TMPDIR`, `TEMP` and `TMP` from the current job’s `RUNNER_TEMP`; this prevents persistent runners from inheriting a deleted temporary directory from an earlier job.

## SDK regeneration ownership

The SDK's `regenerate-derived-artifacts.yml` producer validates each bundle before
its bot publishes a PR. Ownership enforcement accepts these bundles only for
`honua-io/honua-sdk-js`, with the trusted event's numeric bot author and sender
identity, same-repository refs, and the producer's numbered automation branch.
The fetched merge must bind the exact event head and trunk base. Its head must
contain one to four linear commits atop that base, with the producer's commit
subject and every changed path inside the producer allowlist. Base drift fails
closed; the producer already retires stale regeneration PRs.

This exception only removes generated-file ownership findings. Added-path policy,
reserved outputs, changelog ownership, and Terraform backend checks remain active.
No event payload means no exception. The bot identity authenticates publication;
branch names and commit metadata do not authenticate a human-authored PR.
Caller repositories must update their immutable reusable-workflow pin to adopt
this change (and the earlier authenticated Release Please changelog exception).

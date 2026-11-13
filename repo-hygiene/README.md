# Repository hygiene

The reusable workflow checks added paths and protects files owned by trunk/release automation. The added-path rule permits modifying or deleting existing files. A rename into a forbidden location counts as an addition. Candidate Git trees are fetched into a bare repository; candidate code and working-tree files are never executed or checked out.

Any PR addition, modification, deletion or rename of `llms*.txt`, `CHANGELOG.md`, `samples/dist/**`, `docs/bundle-sizes.md` or `api-report/**` is rejected. Terraform backend blocks in changed `.tf` files must keep the same tokenized content; comments, whitespace and changes outside backend blocks are allowed. Backend additions and deletions are rejected too. Gate-input exceptions cannot bypass these ownership checks. File contents are read from Git objects without executing candidate code.

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

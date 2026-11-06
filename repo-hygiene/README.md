# Repository hygiene

The reusable workflow checks only files added by a pull request. Modifying or deleting existing files does not trigger this rule. A rename into a forbidden location counts as an addition. Candidate Git trees are fetched into a bare repository; candidate code and working-tree files are never executed or checked out.

Each repository owns `.github/hygiene.json`, read with `git show` from the trusted base revision, never from the candidate. The shared repository contains no repository-specific data. Land the configuration before introducing the caller. Policy changes take effect on subsequent pull requests after they land.

```json
{
  "roots": [".github/", ".gitignore", "AGENTS.md", "README.md", "src/", "tests/", "docs/", "scripts/", "eng/"],
  "gate_inputs": {"eng/release/audit.v1.json": "Versioned release-gate input"}
}
```

Root files match exactly; directory entries end with `/`. `gate_inputs` permits exact paths with a reason naming their build or release consumer. Keep exceptions short. Source modules and recognized GitHub automation are maintained files. Historical evidence, audits, archives, reports, dated output, scratch directories and backups are rejected. Tools write output beneath gitignored `/artifacts/`; force-adding output there is rejected too. Product repositories cannot add `samples/`; a sample repository can set `"samples": true` in its own configuration.

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

# Runner label lint

Fails when a job that a pull request or `workflow_run` event can reach could resolve `runs-on` to a self-hosted runner for a pull request from a fork. Pull-request jobs from forks must resolve to GitHub-hosted runners. The linter reads `.github/workflows/*.yml` and `*.yaml` as YAML data with PyYAML's safe loader; it never runs anything from the checked repository.

## Rules

A job is checked when its workflow is triggered by `pull_request`, `pull_request_target`, `pull_request_review`, `pull_request_review_comment` or `workflow_run`, or by an event anyone can raise on a public repository (`issue_comment`, `issues`, `discussion`, `discussion_comment`); jobs in a local reusable workflow (`uses: ./.github/workflows/...`) inherit the events of the jobs that call them. A job `if:` narrows this per event: `github.event_name` comparisons (case-insensitive) drop events in each `||` branch, and a fork guard applied by every branch that admits an event covers it, also for the workflows that job calls. Conditions the linter cannot read admit every event.

No context field says whether the actor of `issue_comment`, `issues` or `discussion*` is outside the organization, so the only accepted guard for those events is excluding them by name, in the job `if:` or as an `&&` term before the self-hosted choice (`github.event_name != 'issue_comment' && ...`).

| `runs-on` | Result |
| --- | --- |
| GitHub-hosted label (`ubuntu-*`, `windows-*`, `macos-*` image labels, plus `--allow-label`) | pass |
| `self-hosted`, `honua-light`, `--deny-label` values, any other label, or a list containing one | fail |
| `group:` mapping | fail |
| `${{ matrix.x }}` where every matrix and `include` value is a hosted label | pass |
| `${{ inputs.x }}` where every reachable caller passes, or defaults to, a hosted value | pass |
| The fork-guarded expression below | pass |
| `vars.*`, `needs.*`, `fromJSON(...)`, an unresolvable matrix or input, or partial templating without the guard | fail |

The fork-guarded expression ANDs the guard (either side order inside the parentheses) with the self-hosted choice and ends with a hosted fallback:

```yaml
runs-on: ${{ vars.HONUA_LIGHT_RUNNER && (!github.event.pull_request || github.event.pull_request.head.repo.full_name == github.repository) && (!github.event.workflow_run || github.event.workflow_run.head_repository.full_name == github.repository) && fromJSON(vars.HONUA_LIGHT_RUNNER) || 'ubuntu-latest' }}
```

The `workflow_run` guard is required only when the job is reachable from `workflow_run`. A guard joined with `||`, or an expression with no hosted fallback, fails. Each finding prints `file:line`, the reason and a fix. Unreadable or symlinked workflow files fail closed. A workflow in another repository is not inspected here; for a fork-reachable job that calls one, every `with:` argument whose name mentions `runner`, `runs-on` or `label` must pass the same rules. Lint the called workflow in its own repository.

## Callers

Run on `pull_request_target` and on push to the default branch, not on `pull_request`. For `pull_request`, GitHub runs the caller file from the PR head, so a PR could change or remove the check. For `pull_request_target` the caller comes from the base branch, and the reusable workflow checks out only the `.github/workflows` of `refs/pull/<n>/merge` (or `refs/pull/<n>/head` when GitHub has no merge ref) from the base repository, with `persist-credentials: false`, and parses it as data. Pin an immutable commit; the shared workflow cannot detect a caller that references a branch:

```yaml
name: Runner label lint
on:
  push:
    branches: [trunk]
  pull_request_target:
    types: [opened, synchronize, reopened]
permissions:
  contents: read
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
jobs:
  runner-label-lint:
    uses: honua-io/.github/.github/workflows/runner-label-lint.yml@<sha>
```

Optional inputs: `allow-labels` and `deny-labels`, newline-separated. The linter needs PyYAML, which the `ubuntu-latest` system Python ships; without it the check fails with a message saying so. The required check context is `runner-label-lint / Runner label lint`. The lint covers the workflow files a branch carries; a PR can still edit its own `pull_request` workflows, so the runner group settings that keep self-hosted runners away from fork pull requests remain the primary control.

Run locally against a checkout:

```sh
python3 -I runner-label-lint/lint_runner_labels.py --repo /path/to/repo
python3 -m unittest discover -s runner-label-lint/tests -p 'test_*.py'
```

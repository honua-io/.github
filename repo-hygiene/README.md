# Repository hygiene

The reusable workflow checks added paths and protects files owned by trunk/release automation. The added-path rule permits modifying or deleting existing files. A rename into a forbidden location counts as an addition. Candidate Git trees are fetched into a bare repository; candidate code and working-tree files are never executed or checked out.

Ordinary PR additions, modifications, deletions or renames of `llms*.txt`, `CHANGELOG.md`, `samples/dist/**`, `docs/bundle-sizes.md` or `api-report/**` are rejected. Release Please changelog changes are allowed only when the trusted PR event identifies a recognized bot as both author and sender, both branches belong to the same repository, the head uses the Release Please branch convention for its base, and the event head SHA matches the fetched merge tree. The recognized identities are `honua-io-bot[bot]` and `github-actions[bot]`, checked by numeric user ID and Bot type. This exception covers only `CHANGELOG.md` files; other ownership and added-path rules still apply. The same trusted identities permit generated-file updates only in `honua-io/honua-sdk-js` from `automation/derived-artifacts-<run-id>-<attempt>` branches targeting `trunk`. The fetched merge's first parent must match both the policy base and event base SHA, and its second parent must match the event head SHA. The producer must contribute one to four linear commits, each with the regeneration publisher marker, and change only the explicit SDK producer output allowlist. This exception excludes changelogs and retains backend and added-path rules. Local checks without `--event` retain all ownership restrictions. Terraform backend blocks in changed `.tf` files must keep the same tokenized content; comments, whitespace and changes outside backend blocks are allowed. Backend additions and deletions are rejected too. Gate-input exceptions cannot bypass these ownership checks. File contents are read from Git objects without executing candidate code.

Each repository owns `.github/hygiene.json`, read with `git show` from the trusted base revision, never from the candidate. The shared checker also maintains the explicit SDK producer output contract described above. Land the configuration before introducing the caller. Policy changes take effect on subsequent pull requests after they land.

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
    types: [opened, synchronize, reopened, edited, labeled, unlabeled]
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

## Maintainer release repairs

Maintainer repairs of release PRs retain the changelog exception only when the
fetched release branch has at most four linear commits and every changed changelog
is unchanged from its latest modifying commit, authenticated through GitHub as a
verified, GitHub-signed commit by the PR's recognized release bot. The merge tree
must preserve that changelog exactly. Missing credentials, incomplete history,
manual changelog edits, unsigned commits and API failures retain the ownership
failure. Other path, derived-file and Terraform checks continue independently.
The existing read-only job token performs commit metadata reads; no additional
job, write permission or PR code execution is needed.

## PR bundle policy

The existing `repo-hygiene / Repository hygiene` job also checks PR size and purpose.
A human-authored PR passes when its body closes at least three distinct issues, or
its fetched merge diff adds and deletes at least 300 lines in total, or it has the
`bundle-exception` label and a one-line reason in its body. Bot authors (GitHub
account type `Bot`, including Release Please and Dependabot) bypass only this
bundle rule; all path and ownership checks still apply.

Closing references accept `Closes`, `Fixes`, `Resolves` and their verb variants,
local or cross-repository references, and comma-separated lists. For example,
`Closes #12, #13, honua-io/other#14` counts three distinct issues. Repeating a
reference does not count again; comments, code examples and blockquotes do not
count. The checker does not judge whether the issues are related: reviewers own
that decision. Binary files and unchanged renames contribute zero lines. The line count comes from the
fetched Git trees; candidate code is never executed.

Use this body metadata for a permitted exception and lane accounting:

```text
Lane: s-ci-gate
Bundle-exception: blocking red — restore the required check blocking the release PR
```

Permitted exception categories are `trunk-red`, `security high` and `blocking red`.
A label alone, an empty reason or an unrelated category fails. Removing the label
removes the exception. Callers must include `edited`, `labeled` and `unlabeled`
events so metadata changes rerun the existing required job.

After this shared policy lands, update **every caller's immutable policy SHA**
and event list. Older pinned callers continue to enforce their pinned policy;
merging the shared change alone does not activate the bundle check in those
repositories. No new required check or ruleset setting is needed.

`Weekly bundle exceptions` runs Mondays and on manual dispatch. It uses the
existing organization bot App credentials (`BOT_APP_ID` / `BOT_APP_PRIVATE_KEY`)
with read-only PR permission to print merged, labelled exceptions by `Lane:` in
the job log and Actions summary. PRs without lane metadata are explicitly
unattributed. The report covers the past seven UTC calendar days and fails on
incomplete or over-limit search results. Counts reflect labels and bodies at
report time; removing a label after merge removes that PR from this report.
The workflow verifies via an authenticated read-only App API request that the
installation belongs to honua-io, is active, and covers all repositories before
running organization search. A selected-repository installation fails instead of
silently omitting inaccessible repositories. Its credentials must be available
to this repository; missing access fails the report. The local command assumes
your authenticated token has the same organization coverage.

Run the same report locally with authenticated read access:

```sh
python3 -I repo-hygiene/bundle.py summary --since 2026-11-09
```

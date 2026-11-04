# clean-code

Shared Clean Code tooling for honua-io repositories. The review rubric every repository's AGENTS.md points to is [RUBRIC.md](RUBRIC.md).

## PR check

`.github/workflows/clean-code.yml` runs on every pull request in the calling repository. It is a ratchet: it reports only what the PR makes worse, so existing code never fails it. Comment rules judge added lines. Everything else compares head with base. Each unchanged head line maps to the base line it came from. Functions are paired one to one (`clean_code/correspondence.py`): first by the unchanged lines each owns directly (not through a nested function), then by a unique same name, then by similar text. So renames, reorders, overloads and edits elsewhere in the file keep their baseline, and when a function is split only one half continues it. A touched function may not exceed a budget by more than its base counterpart did, nor gain a boolean parameter; a function without a counterpart is new. ruff and ESLint run on base and head copies of the changed files: a function-level finding (parameters, statements, complexity) is new unless the counterpart had it with at least the same measure, and a line-level finding is new unless its unchanged base line had it. Each finding is an annotation titled with its Clean Code smell code (see the rubric: N, F, C, G, T; Ch10 is chapter 10, small classes).

```yaml
# .github/workflows/clean-code.yml in a calling repository
name: Clean code
on:
  pull_request:
    types: [opened, synchronize, reopened, edited]
permissions:
  contents: read
jobs:
  clean-code:
    uses: honua-io/.github/.github/workflows/clean-code.yml@<sha>
    with:
      xml-docs: forbid        # or public-summary for published SDKs
      exclude: |              # optional, extra globs to skip
        docs/examples/**
```

`edited` re-runs the check when the PR body changes, so adding an exception takes effect without a push.

### Rules

| Smell | Rule | Finds | Languages | Severity |
| --- | --- | --- | --- | --- |
| C1 | `clean-code/history-comment` | Change history in a comment | all source | block |
| C1 | `clean-code/reviewer-note` | Reviewer note in a comment | all source | block |
| C1 | `clean-code/ticket-reference` | Ticket or PR reference in a comment | all source | block |
| C1 | `clean-code/xml-doc` | XML doc comment in application code | C# | block |
| C3 | `clean-code/redundant-comment` | Comment restates the next line of code | all source | advisory |
| C5 | `clean-code/commented-out-code` | Commented-out code | C#, Terraform, shell | block |
| C5 | `eslint/sonarjs/no-commented-code` | Commented-out code | TS/JS | block |
| C5 | `ruff/ERA001` | Commented-out code | Python | block |
| Ch10 | `clean-code/large-file-growth` | File over 800 lines grew | all source | block |
| Ch10 | `clean-code/new-file-size` | New file over 400 lines | all source | block |
| F1 | `clean-code/too-many-parameters` | More than 4 parameters | C# | block |
| F1 | `eslint/max-params` | More than 4 parameters | TS/JS | block |
| F1 | `ruff/PLR0913` | More than 4 parameters | Python | block |
| F3 | `clean-code/flag-argument` | Boolean flag parameter | C#, TS/JS, Python | block |
| F3 | `ruff/FBT003` | Boolean positional argument in a call | Python | advisory |
| G25 | `eslint/no-magic-numbers` | Magic number | TS/JS | advisory |
| G25 | `eslint/sonarjs/no-duplicate-string` | Duplicated string literal | TS/JS | advisory |
| G25 | `ruff/PLR2004` | Magic number | Python | advisory |
| G30 | `clean-code/function-length` | Function over 60 lines | Python, C#, TS/JS | block |
| G30 | `eslint/complexity` | Cyclomatic complexity over 10 | TS/JS | advisory |
| G30 | `eslint/sonarjs/cognitive-complexity` | Cognitive complexity over 15 | TS/JS | advisory |
| G30 | `ruff/C901` | Cyclomatic complexity over 10 | Python | advisory |
| G30 | `ruff/PLR0915` | Too many statements | Python | advisory |
| G34 | `eslint/max-depth` | Nesting deeper than 2 | TS/JS | advisory |
| G5 | `clean-code/duplication` | Duplicated block (15+ lines, 100+ tokens) | all source | block |
| G5 | `eslint/sonarjs/no-identical-functions` | Identical functions | TS/JS | block |

`block` findings fail the job; `advisory` findings are notices. One tool owns each rule per language: ruff for Python, ESLint with `eslint-plugin-sonarjs` for TS/JS, and the lexers in `clean_code/` for C#, Terraform, shell and the cross-language rules. Function length for TS/JS comes from the TypeScript parser rather than ESLint, so `describe`/`it` callbacks don't count as long functions. C# has no compiler-backed analyzer here; that would need a build, and this check runs on changed files only.

### Budgets

`budgets.json` holds every threshold; `eslint.config.mjs` and the ruff invocation read it.

| Budget | Value | Rule |
| --- | --- | --- |
| Function length | 60 lines (the rubric's soft target is about 40) | G30 |
| Parameters | 4 (constructors exempt in C#, for dependency injection) | F1 |
| New file | 400 lines | Ch10 |
| Large file that may not grow | 800 lines | Ch10 |
| Duplicated block | 15 consecutive significant lines and 100 tokens | G5 |
| Cyclomatic / cognitive complexity | 10 / 15 | G30 |
| Nesting depth | 2 | G34 |

Duplication: every run of 15 significant lines (blank, comment-only, punctuation-only and import/using lines are skipped) that touches an added line is hashed per language and counted across the repository at base and at head. More copies at head than at base is a clone the PR introduced, including one completed by a single line; a moved block is not.

Skipped as generated or vendored: `node_modules`, `dist`, `build`, `vendor`, `third_party`, `wwwroot/lib`, `Migrations`, `generated`, snapshots, `*.min.*`, `*.bundle.*`, hashed bundles under `assets/`, `*.d.ts`, `*.g.cs`, `*.Designer.cs`, protobuf output, symlinks and submodules; callers add globs with `exclude`.

Comments (C1): bare `#123`, `SEC-12`, `honua-*#12`, honua-io issue or PR links, "PR 12"/"issue 12", history wording ("previously", "no longer", "used to be", "was changed", "now we") and reviewer notes. References to external upstreams such as `dotnet/runtime#12345` are allowed: they explain a workaround. `xml-docs: forbid` flags every new `///` line; `public-summary` allows only a one-line `/// <summary>` and flags the rest.

### Exceptions and declarations in the PR body

- `quality-exception: <reason>` turns blocking findings into warnings. The job passes, and the summary logs the reason with every finding. A marker without a reason does nothing.
- A line `clean-code: comment-only` also runs the comment-only verifier below and fails unless the diff is proven comment- and whitespace-only; a `quality-exception` does not waive that. A second line `clean-code: docstring-removal` lets it delete Python docstrings. Each declaration must be alone on its line, so prose that mentions one does not trigger it.

## Comment-only diff verifier

Proves that a diff changes only comments and whitespace, so a mass comment cleanup can merge on proof instead of line-by-line review.

```sh
clean-code/install.sh /tmp/clean-code-venv      # the pinned linters, once
python3 -I clean-code/verify_comment_only.py --repo <repo> --base origin/trunk --head HEAD
```

It lexes both sides of every changed file, drops comments, and compares the code token streams. Any other difference fails, with the first differing line on each side. Only whitespace that can change meaning counts: line breaks in TypeScript, JavaScript and Terraform (automatic semicolons, attribute separators), Python indentation, and spaces that keep two tokens apart.

| Language | Lexer | Kept whole, never treated as comments |
| --- | --- | --- |
| C# (`.cs`, `.csx`) | `clean_code/dialects.py` | regular, verbatim, interpolated and raw strings (including `$$"""` holes); char literals; preprocessor lines, exactly as written up to an unquoted `//` (`#region` text is code). Every C# line terminator ends a `//` comment: CR, LF, CRLF, NEL, U+2028, U+2029 |
| Python (`.py`, `.pyi`) | `tokenize` + `ast` | strings, docstrings (see below) |
| TypeScript, JavaScript (`.ts`, `.tsx`, `.js`, `.mjs`, ...) | the TypeScript parser (`ts_lexer.cjs`) | strings, template literals, regex literals, JSX text children, exactly and one by one; only whitespace-only text spanning a line break is dropped, as the JSX transform drops it (so deleting `{/* */}` between two texts fails) |
| Terraform, HCL (`.tf`, `.tfvars`, `.hcl`) | `clean_code/dialects.py` | template strings and heredocs |

Any other changed file fails, as does an added, deleted or renamed file, a file mode change, a symlink or submodule, a file that is not UTF-8, a path containing a line break, and Python or Terraform with lone-CR line endings.

Python docstrings are code. `--allow-docstring-removal` lets a PR delete docstrings that restate the code: every docstring left at head must be byte-identical to the one in the same place at base, so none can be added, edited or moved. Declare it in the PR body.

## Tests

```sh
cd clean-code && PATH="$(./install.sh /tmp/clean-code-venv):$PATH" python3 -m unittest discover -s tests -t .
```

Each `tests/fixtures/rules/<rule>/` holds `bad.*` files that must trigger the rule and `good.*` files that must not.
Each `tests/fixtures/comment_only/<case>/` holds a `base` and `head` file. `same-*` cases must verify as comment-only, `diff-*` cases must fail, and a `-removable` suffix runs with docstring removal allowed.

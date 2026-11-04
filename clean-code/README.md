# clean-code

Shared Clean Code tooling for honua-io repositories.

## Comment-only diff verifier

Proves that a diff changes only comments and whitespace, so a mass comment cleanup can merge on proof instead of line-by-line review.

```sh
npm ci --prefix clean-code --ignore-scripts      # the TypeScript parser, once
python3 -I clean-code/verify_comment_only.py --repo <repo> --base origin/trunk --head HEAD
```

It lexes both sides of every changed file, drops comments, and compares the code token streams. Any other difference fails, with the first differing line on each side. Only whitespace that can change meaning counts: line breaks in TypeScript, JavaScript and Terraform (automatic semicolons, attribute separators), Python indentation, and spaces that keep two tokens apart.

| Language | Lexer | Kept whole, never treated as comments |
| --- | --- | --- |
| C# (`.cs`, `.csx`) | `clean_code/dialects.py` | regular, verbatim, interpolated and raw strings; char literals; preprocessor lines (`#region` text is code) |
| Python (`.py`, `.pyi`) | `tokenize` + `ast` | strings, docstrings (see below) |
| TypeScript, JavaScript (`.ts`, `.tsx`, `.js`, `.mjs`, ...) | the TypeScript parser (`ts_lexer.cjs`) | strings, template literals, regex literals, JSX text |
| Terraform, HCL (`.tf`, `.tfvars`, `.hcl`) | `clean_code/dialects.py` | template strings and heredocs |

Any other changed file, and any added, deleted or renamed file, fails.

Python docstrings are code. `--allow-docstring-removal` lets a PR delete docstrings that restate the code, never add or edit one; declare it in the PR body.

## Tests

```sh
cd clean-code && npm ci --ignore-scripts && python3 -m unittest discover -s tests -t .
```

Each `tests/fixtures/comment_only/<case>/` holds a `base` and `head` file. `same-*` cases must verify as comment-only, `diff-*` cases must fail, and a `-removable` suffix runs with docstring removal allowed.

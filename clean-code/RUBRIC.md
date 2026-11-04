# Clean Code review rubric (Robert C. Martin, *Clean Code*)

Every review (people, Codex, Claude) applies this rubric in addition to correctness. The `Clean code` PR check (README.md) enforces the rules a tool can decide.
- **Cite findings by smell code** (e.g. "G5 Duplication", "C3 Redundant comment", "F3 Flag argument").
- **Severity:**
  - BLOCK for any G5, C2–C5, F1–F3 or N1 finding in new or changed code, and for a function or class over budget without a stated reason;
  - suggest for the rest.
- **Scope:** judge only the code the PR adds or changes, plus anything it was required to consolidate.

## Names (N)
- **N1** Choose descriptive, intention-revealing names: the name answers why it exists, what it does, how it's used.
- **N2** Choose names at the right level of abstraction.
- **N3** Use standard nomenclature: domain terms such as OGC, FeatureServer and MCP; pattern names.
- **N4** Unambiguous names; no disinformation; meaningful distinctions (no `data` vs `info`, `Manager`, `Processor` padding).
- **N5** Name length matches scope.
- **N6** No encodings or prefixes.
- **N7** Names describe side effects (`GetOrCreate…`, not `Get…`).

## Functions (F, plus chapter 3)
- **Small, and do one thing:** a single level of abstraction. Follow the stepdown rule (read top-down, high level to detail).
- **Size budgets:** functions ≤ about 40 lines; nesting ≤ 2 levels, with early returns.
- **F1** Too many arguments: ≤ 3, otherwise a parameter object.
- **F2** Output arguments: avoid.
- **F3** Flag (boolean) arguments: split the function instead.
- **F4** Dead functions: delete.
- **No hidden side effects.** Command-query separation.
- Prefer exceptions or typed results to error codes, and extract the try/catch body.

## Comments (C, plus chapter 4)
- **The rule:** comments are a failure to express in code. Rename or extract first.
- **Allowed:** legal notices; intent or "why" the code can't express; clarifying an external format; warnings of consequences; TODO with an owner; public-API docs where the API is genuinely public.
- **C1** Inappropriate information: history, ticket or PR numbers, authors, change logs. These belong in git.
- **C2** Obsolete comment.
- **C3** Redundant comment: it restates the code.
- **C4** Poorly written or rambling, essay-length comments.
- **C5** Commented-out code: delete.
- **Also banned:** noise comments, journal comments, position markers and banners, closing-brace comments, and mandated XML docs on internal members.

## General (G), the most common in this codebase
- **G5** Duplication (DRY), the top smell. Consolidate copies; use polymorphism or a shared helper for repeated switch and if chains.
- **G6** Code at the wrong level of abstraction.
- **G8** Too much information: wide interfaces, many public members.
- **G9** Dead code.
- **G10** Vertical separation: declare things close to their use.
- **G11** Inconsistency: the same concept done several ways (errors, auth, config).
- **G12** Clutter: unused variables, default constructors, noise.
- **G14** Feature envy.
- **G15** Selector arguments.
- **G16** Obscured intent.
- **G17** Misplaced responsibility.
- **G18** Inappropriate static.
- **G19** Use explanatory variables.
- **G20** Function names say what they do.
- **G23** Prefer polymorphism to if/else and switch on type.
- **G25** Replace magic numbers and strings with named constants.
- **G28** Encapsulate conditionals.
- **G29** Avoid negative conditionals.
- **G30** Functions do one thing.
- **G31** Hidden temporal couplings.
- **G34** Functions descend one level of abstraction.
- **G36** Avoid transitive navigation (Law of Demeter).

## Classes and objects (chapters 6 and 10)
- **Small and single responsibility:** one reason to change, high cohesion. Classes and files ≤ about 400 lines.
- **Split by responsibility, not length.** Partial-class sprawl is not decomposition.
- **Open/Closed and Dependency Inversion only where real variation exists.** Single-implementation interfaces "for later" are G12 clutter.
- **Objects hide data and expose behaviour; data structures expose data.** No hybrids.
- **Don't return or pass null** where a typed empty or optional fits.

## Tests (T, plus chapter 9)
- **F.I.R.S.T.:** fast, independent, repeatable, self-validating, timely.
- **One concept per test.** Readable build–operate–check structure.
- **T1** Insufficient tests.
- **T3** Don't skip trivial tests.
- **T5** Test boundary conditions.
- **T9** Tests should be fast.
- **No giant inline fixtures.** Parametrize repetition.

## Simple design (Kent Beck, as cited in *Clean Code*, chapter 12)
In priority order:
1. Runs all the tests.
2. Contains no duplication.
3. Expresses the intent of the programmer.
4. Minimises the number of classes and methods.

## Review output
- **The first line is the verdict** (`**MERGE-OK — review at <sha>.**` / `**BLOCK — …**`).
- **Then the findings,** each with:
  - the smell code;
  - file:line;
  - a quote of at most 5 lines;
  - the concrete fix.
- **End with a one-line Clean Code summary:** "names / functions / comments / DRY / classes: ok | issues".

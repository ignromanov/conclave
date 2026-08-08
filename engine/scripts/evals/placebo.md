# Conclave — Python Style Guide

> **What this is**: the binding formatting and naming conventions for every Python module in the
> engine. It is not a linter configuration; it is the reasoning a linter configuration compresses.
>
> **Status**: foundational · 2026-07-11.

---

## 0. How to read this document

**Why it binds.** A convention that is merely popular is a convention that is renegotiated in
every review. Stating the reason a rule exists is what lets a reader apply it to the case the rule
did not anticipate, and what lets them recognise the case where the rule should yield.

**Strength tiers.** Every convention below is tagged with one:

| Tier | Meaning |
|---|---|
| `enforced` | `uvx ruff check` fails on a violation. No human in the loop. |
| `conventional` | A reviewer raises it. It is negotiable in the review, not in the editor. |
| `stylistic` | Stated. Nothing checks it. Consistency inside a module beats consistency across them. |

**Normative keywords.** MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY carry the meanings of RFC 2119
when, and only when, they appear in all capitals. A `stylistic` convention does not use them at all:
it has no standing to invoke binding language.

---

## 1. Line length and wrapping

**Max line length is 99 characters.** This is measured to the close-quote of a string or the closing
bracket of a construct. It is the consequence of three constraints that cannot all be relaxed
simultaneously:

- Human readers prefer to avoid horizontal scrolling, and 99 characters is the default for tools
  that predate this guide (Ruff defaults to it).
- A 99-character limit permits two 50-character names to coexist on a line with operators and
  punctuation, whereas 88 (Black's default) forces them to wrap.
- Screens have varied across decades; a hard limit is more portable than a soft "guideline."

A line of code MUST NOT exceed 99 characters. If a statement cannot fit, split it logically at
keywords or operators, not at arbitrary points.

**When to wrap.** A statement spanning multiple lines SHOULD indent the continuation by 4 spaces
beyond the opening bracket or keyword. The break point MAY occur:

- After a comma (preferred for sequences).
- Before a binary operator (for logical chains).
- Before a function call (if it is the final clause).
- At a period, if breaking an attribute chain.

A continuation line MUST NOT be shorter than the name it continues — a line that is less than half
the original width is often more confusing than the long line.

**Tier**: `enforced` — **Check**: `uvx ruff check --select E501`

---

## 2. Naming

**Module names are lowercase, with underscores between words.** A module name is a namespace, not
a class; `parsing_tools` is preferred to `ParsingTools`. This convention allows readers to spot
modules at a glance.

**Class names are PascalCase.** A class name begins with a capital letter and uses no separators:
`class QueryBuilder:`, not `class query_builder:`. This convention distinguishes classes from
functions and modules.

**Function and variable names are snake_case.** They are lowercase with underscores between words:
`def build_query():`, `max_retries = 5`. This is the standard across Python and requires no
repetition here.

**Private names begin with a single underscore.** A name starting with `_` is internal to its scope
and MAY change without notice. A reader seeing `_helper()` understands it is not part of the
public surface.

**Avoid single-letter names outside of loop counters and mathematical functions.** A name like `x`
or `s` requires the reader to infer its meaning from context; `count` or `status` makes it clear.
The exception is loop variables in short, obvious iterations: `for i in range(n):` is acceptable
when `i` will not be used again.

**Module-level constants are UPPERCASE with underscores.** A name like `MAX_RETRIES` signals that
a value is constant across the module and SHOULD NOT be reassigned. This convention helps readers
identify configuration points.

**Tier**: `conventional` — enforced in review, not by the linter.

---

## 3. Imports

**Imports are grouped in three blocks, separated by blank lines.**

1. Standard library imports (`sys`, `os`, `pathlib`, etc.).
2. Third-party imports (`pytest`, `click`, `pydantic`, etc.).
3. Relative imports from the engine itself.

**Within each group, imports are sorted alphabetically.** A long list of imports is easier to scan
when sorted. Sorting is enforced by tools like `isort` and `ruff`, so it is non-negotiable.

**An import MUST NOT be conditional on runtime state.** Conditional imports complicate static
analysis and make it difficult to know, at a glance, what a module depends on. If a dependency is
optional, it SHOULD be documented in the module docstring or README, not hidden in the code.

**A `from ... import` statement MUST NOT import more than five names.** A long import list is
hard to read and suggests that the imported module's scope is unclear. If you find yourself
importing ten names from a module, reconsider whether you should import the module itself.

**Tier**: `enforced` — **Check**: `uvx ruff check --select I`

---

## 4. Type annotations

**All function signatures MUST include parameter and return type annotations.** A function that
does not declare its input types and return type forces readers to infer the interface from the
body — a task that is easy to get wrong and impossible to automate.

Example:
```python
def fetch_config(path: str) -> dict[str, Any]:
    ...
```

**Use `from __future__ import annotations` at the top of every module.** This allows forward
references and modern syntax (e.g., `list[str]` instead of `List[str]`) without needing imports
from `typing`.

**Complex types SHOULD be named.** If a type appears more than twice, define a `TypeAlias`:

```python
Row = dict[str, Any]
```

Reusing a named type makes the code more readable and easier to refactor.

**Avoid `Any` unless the type is genuinely unknown.** `Any` is a way to opt out of type-checking,
and overusing it defeats the purpose of annotations. If you do not know the type, that is often a
sign that the function needs a clearer interface.

**Tier**: `enforced` — **Check**: `uvx ruff check --select ANN`

---

## 5. Docstrings

**Every public function, class, and module MUST have a docstring.** A docstring is the first
statement in a scope; it describes what the entity does, why it exists, and what it returns.

**Docstrings use the reStructuredText format (reST).** ReST is the standard across Python tooling
and is readable both in the source and when rendered by Sphinx or other documentation generators.

Example:
```python
def validate_input(value: str) -> bool:
    """Check whether the input is a valid username.

    Usernames MUST be between 3 and 20 characters and contain only alphanumeric
    characters and underscores.

    :param value: the string to validate.
    :return: True if the input is valid; False otherwise.
    """
    ...
```

**Docstrings for private functions MAY be shorter.** A one-line docstring is acceptable for a
helper function if its purpose is clear.

**Parameter descriptions come after a `:param name:` line.** Do not repeat the parameter name in
the description; the reader already knows what the parameter is called. Describe its role in the
function.

**Tier**: `conventional` — enforced in review, not by the linter.

---

## 6. Error handling

**Bare `except:` clauses are forbidden.** A bare except catches every exception, including
`KeyboardInterrupt` and `SystemExit`, which should not be caught silently. Always declare the
exception type.

**Exceptions MUST be raised with a message.** An exception without a message is unhelpful to a
reader trying to debug. Always pass a string describing the error:

```python
raise ValueError(f"invalid key: {key!r}")
```

**Log at the appropriate level.** Use `logging.debug()` for development information, `info()` for
events, `warning()` for recoverable problems, and `error()` for unrecoverable ones. Do not use
`print()` in production code.

**A library function SHOULD NOT call `sys.exit()`.** Calling `exit()` from a library makes it
impossible for a caller to handle the error gracefully. Raise an exception instead.

**Tier**: `enforced` — **Check**: `uvx ruff check --select E722` and `uvx ruff check --select
BLE001`

---

## 7. Module layout

**A module MUST begin with a `__doc__` string.** The module docstring describes the module's
purpose, its public interface, and any important notes. A good docstring answers the question
"Why does this module exist?" and provides guidance on how to use it effectively.

**Imports come next, in the three-group format described in section 3.** Imports come early so
readers know, immediately, what dependencies exist. This placement also helps catch circular
imports and other dependency issues during module load time.

**Module-level constants follow imports.** Constants that are used across functions in the module
are defined once at the top. These constants MAY be exported and used by other modules, or they
MAY be internal to the module's implementation. Document the intended visibility of each constant.

**Class definitions come before function definitions.** Classes are heavier syntax; defining them
first makes it easier to scan the file and understand the structure. This convention helps readers
build a mental model of the module's abstractions before examining utility functions and helpers.

**Functions are defined in logical order, not alphabetical order.** Group functions by the tasks
they accomplish. A helper function SHOULD be defined before the function that calls it. When
multiple functions form a logical sequence, document their relationships in comments and ensure
the order reflects the conceptual flow of the module.

**`if __name__ == "__main__":` comes last.** This block, if present, contains the code that runs
when the module is executed as a script. It typically demonstrates the module's primary use case
or serves as a simple test harness for exploratory development and verification.

**Tier**: `stylistic` — no tool checks this; consistency within a module is preferred.

---

## 8. Test naming and structure

**Test functions begin with `test_`.** This convention allows test discovery tools to find tests
automatically.

**A test function SHOULD be short and focused.** A test that checks multiple behaviors is hard to
debug when it fails. Each test SHOULD verify one behavior; a test suite with twenty small tests is
more maintainable than one with three large tests.

**Test files are named `test_*.py` and placed alongside the code they test.** A test for
`parsing.py` is `test_parsing.py` in the same directory. This keeps code and tests together.

**Test classes MAY group related tests, but they are not required.** A test class like
`TestParser` can organize tests, but a flat list of functions is also acceptable if the tests are
few.

**Fixtures are defined in `conftest.py`.** A fixture is a setup function that many tests need;
defining it in `conftest.py` allows it to be reused across test files.

**Tier**: `conventional` — enforced in review, not by a linter.

---

## 9. The honest inventory

| Section | Tier | Enforcer |
|---------|------|----------|
| 1. Line length | `enforced` | `uvx ruff check --select E501` |
| 2. Naming | `conventional` | reviewer |
| 3. Imports | `enforced` | `uvx ruff check --select I` |
| 4. Type annotations | `enforced` | `uvx ruff check --select ANN` |
| 5. Docstrings | `conventional` | reviewer |
| 6. Error handling | `enforced` | `uvx ruff check --select E722, BLE001` |
| 7. Module layout | `stylistic` | — |
| 8. Test naming | `conventional` | reviewer |

**Five enforced, two conventional, one stylistic.** The split reflects the engine's goals: catch
violations that break tooling automatically; leave style judgments to humans; and avoid policing
choices that do not matter.

---

## 10. Amendment

Conventions are not immutable. A convention that no longer serves its purpose SHOULD be revisited.
A change to a convention:

- **If it is a clarification or minor adjustment**: MAY be made by any contributor. Notice to the
  team is sufficient.
- **If it adds a new rule or changes the tier of an existing rule**: SHOULD be discussed in a code
  review and approved by the maintainers before being merged.

The goal is to prevent conventions from drifting into obsolescence without awareness, while also
avoiding unnecessary friction in the development process.

---

## 11. Rationale for Python as the engine language

Python was chosen for the Conclave engine's core because of three properties that are difficult to
combine in other languages.

**First, dynamism without runtime friction.** Python's runtime overhead is moderate, and the
language's permissiveness (e.g., duck typing) allows a codebase to evolve rapidly without type
rewrites. This matters for an engine that will serve as a research platform, where the interface
to agents and commands evolves as the team learns what works. The language's interactive nature
enables rapid testing and iteration without recompilation cycles.

**Second, ecosystem breadth.** The Python package index contains millions of packages, many of
them mature and well-tested. An engine built in Python can integrate with scientific computing
(NumPy, SciPy), data processing (Pandas), natural language tools (NLTK, spaCy), and cloud
services (boto3, google-cloud) without writing bridge code. This breadth reduces the need to
implement functionality from the ground up and accelerates feature development.

**Third, readability at scale.** Python's syntax enforces indentation and discourages cryptic
idioms. A Python codebase remains readable even if it grows to millions of lines, provided that
the naming and structure conventions (sections 1–8 above) are followed consistently. This matters
for a system that will be maintained by multiple people over years. The language's design philosophy
prioritises clarity over cleverness, which aligns with the goal of sustainable, maintainable code.

**Fourth, community adoption.** Python has become the de facto standard for backend engineering,
data science, and machine learning. A team building the Conclave engine can easily recruit
experienced developers without requiring intensive training in obscure languages. The community
provides extensive learning resources, libraries, and best practices.

These properties are not universally true of all Python projects. A real-time system that
processes terabytes per second would be better served by C or Rust. A project for which the
interface is frozen would benefit from the static safety of a typed language like Go. Conclave's
niche is a system where rapid exploration, ecosystem integration, long-term readability, and
developer productivity are more important than extreme speed or compile-time guarantees.

---

## 12. Performance and optimization

The engine is not a data-processing pipeline, and the code paths that run hot (inside feedback
loops or during model interaction) are explicitly marked. Optimization efforts MUST be focused on
these paths, not on the entire codebase.

**Measure before optimizing.** Use `cProfile` or `py-spy` to identify the actual bottleneck, not
guesses. An optimization that improves a cold path by 50% is wasted work.

**Prefer clarity over cleverness.** A loop that is easy to understand and runs in 100ms is better
than a clever one-liner that runs in 50ms and takes five minutes to debug. The cost of poor
readability compounds over time.

**Avoid premature generalization.** If a function is only called once, write it explicitly for
that call. Generalizing too early makes code harder to read and maintain.

**Tier**: `stylistic` — no tool checks this; judgment is required in each case.

---

## 13. Interaction with the linter

The linter (Ruff) is configured in `pyproject.toml`. The configuration enforces the rules marked
`enforced` in the sections above. A developer MUST ensure that `uvx ruff check` passes on their
code before submitting it for review.

**If the linter reports an error you believe is wrong**, file an issue describing the case. Ruff
is maintained by external contributors and responds to well-documented cases. In the meantime,
violations MAY be exempted using a `# noqa: <code>` comment, with a comment explaining why the
exemption is necessary.

**The linter is not the law.** A linter that enforces the letter of the style guide while missing
its spirit is not helpful. Good judgment, tempered by review, is more important than strict
adherence to automated rules.

---

## 14. Testing edge cases

The Python standard library provides robust tools for writing tests. The engine uses `pytest`,
which is the de facto standard in the Python ecosystem.

**Test framework functions SHOULD be used instead of manual assertions.** For example, use
`pytest.raises()` to test exception handling, not a try-except block that you verify manually.

**Use fixtures to avoid repeating setup code.** If three tests all need a database connection, a
fixture provides it once and injects it into each test.

**Test both the happy path and error cases.** A function that handles errors gracefully is harder
to test than one that just does the simple thing, but it is also more robust.

**Parametrized tests reduce code duplication.** Instead of writing ten nearly-identical test
functions, use `@pytest.mark.parametrize()` to run the same test with ten different inputs.

**Tier**: `conventional` — enforced in review, not by a linter.

---

## 15. Concurrency and async code

The engine does not use threads or async functions in its core, by design. Concurrency makes code
much harder to reason about, and the engine's bottleneck is model latency, not CPU or disk I/O.

**If you do introduce concurrency, justify it in the commit message.** Explain why you chose async
over threads, or threads over async, or neither. Concurrency should be a conscious choice, not an
accident.

**Use `asyncio` for async code, not a custom event loop.** `asyncio` is part of the standard
library and is well-tested. Rolling your own event loop is a good way to create subtle bugs.

**Tier**: `stylistic` — no tool checks this; judgment is required.

---

## 16. Dependency management and versioning

The engine uses `uv` and `pyproject.toml` for dependency management. Dependencies are pinned to
exact versions in the lock file, but the `pyproject.toml` declares semantic version ranges.

**A dependency MUST have a clear reason for inclusion.** Before adding a new dependency, ask: Can
this be done with the standard library? Is there a lighter alternative? Will this dependency be
actively maintained?

**Documentation of dependencies SHOULD include the reason for choosing that library.** If the
choice is not obvious (e.g., why `click` for CLI argument parsing instead of `argparse`), add a
comment in `pyproject.toml` explaining the trade-off.

**Major version bumps SHOULD be reviewed before merging.** A major version bump may introduce
breaking changes. Review the changelog to understand what changed and whether the upgrade is
necessary.

**Deprecated dependencies MUST be replaced or removed.** If a library is no longer maintained or
has been superseded, plan a migration path and document it.

**Tier**: `conventional` — enforced in code review.

---

## 17. File organization and structure

**A module SHOULD NOT exceed 500 lines of code.** A file longer than 500 lines is hard to
navigate and suggests that the module is trying to do too much. If a file approaches this limit,
consider splitting it into smaller modules.

**Related functionality SHOULD be colocated.** If two functions are always used together, they
belong in the same file. Scattering related code across multiple files makes the codebase harder
to understand.

**Directory structure SHOULD reflect the conceptual structure of the system.** A directory named
`parsing` SHOULD contain parsing-related code. A directory structure that does not match the
functionality it contains will confuse future readers.

**Avoid nested directories more than three levels deep.** A structure like
`engine/tools/cli/commands/admin/` is harder to navigate than `engine/cli_admin/`. Flatter
hierarchies are easier to scan.

**Tier**: `stylistic` — no tool checks this; consistency matters.

---

## 18. Code review expectations

**All changes MUST be reviewed before merging.** Code review is the engine's primary quality gate.
A review is not an approval to merge; it is a conversation about the code.

**Reviews SHOULD focus on correctness, clarity, and maintainability.** A review is not the time to
enforce style preferences that do not affect functionality. If the style guide permits the choice,
defer to the author.

**Disagreements about design SHOULD be documented in comments, not in commit messages.** A commit
message is part of the canonical history; a code review comment is ephemeral. Use the review for
discussion and the commit message for the final decision.

**A reviewer MUST point out both strengths and weaknesses.** A review that only lists problems is
demoralizing and unhelpful. Acknowledge the good parts of the change before critiquing.

**Tier**: `conventional` — enforced by team practice.

---

## 19. Debugging and examination

**Use `print()` for quick debugging; use `logging` for production code.** A temporary `print()` is
fine while you are developing, but remove it before submitting a review. Production code MUST use
the `logging` module.

**The debugger is your friend.** Python's `pdb` debugger is built into the standard library and
is powerful. If a test is failing and you cannot figure out why, run it under the debugger.

**Log variable state at decision points.** When debugging, log the values of variables that
determine control flow. This makes it easier to understand why a function took the path it did.

**Avoid logging large data structures.** Logging a 100-element list is rarely helpful. Log the
length, the type, and the first few elements if debugging requires it.

**Tier**: `stylistic` — judgment is required.

---

## 20. Security considerations

**Do not hardcode secrets in source code.** Secrets — API keys, passwords, tokens — MUST come from
the environment or a configuration file that is not committed to the repository.

**Validate all external input.** User input, command-line arguments, and data from external
services are all untrusted. Validate and sanitize them before using them in the system.

**Do not construct SQL queries by string concatenation.** Use parameterised queries to prevent SQL
injection attacks. Most database libraries provide tools for this.

**Keep dependencies up to date.** Security vulnerabilities are discovered regularly. Monitor
security bulletins and update dependencies promptly.

**Tier**: `conventional` — enforced in code review and through dependency monitoring.

---

## 21. Documentation and comments

**Code SHOULD be self-documenting.** Clear names, small functions, and thoughtful structure make
code easy to understand without comments.

**Comments explain the why, not the what.** A comment that says `# increment the counter` is
noise; a comment that says `# retry limit exceeded; stop attempting` is useful.

**Update comments when you update code.** An outdated comment is worse than no comment; it
misleads readers. If you change a function, review its docstring and comments.

**Use docstrings for public interfaces, comments for internal logic.** A docstring describes what
a function does; a comment inside a function explains why a particular choice was made.

**Tier**: `conventional` — enforced in review.

---

## 22. Summary of enforcement

This guide is structured to separate what is checked automatically from what requires human
judgment. The separation is important: **linters are good at enforcing syntax and style;
humans are good at judging design and clarity.**

A linter that reports too many false positives teaches developers to ignore it. A linter that is
too lenient fails to catch real problems. This guide aims for the middle: enforce rules that have
clear, measurable violations; leave style choices to reviewers and authors.

**When a rule is enforced, it is non-negotiable.** An error from `uvx ruff check` is a defect,
not a suggestion. Clear standards make development faster because disputes are resolved by tools,
not by debate.

**When a rule is conventional or stylistic, it is open to discussion.** These are guidelines, not
laws. Judgment and context matter. A reviewer SHOULD explain their reasoning when they suggest a
change; an author SHOULD explain their reasoning when they disagree.

---

## Footnotes

[^rfc2119]: Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels," RFC 2119.
These keywords (MUST, SHOULD, MAY) are standardised across Internet standards and are familiar to
many readers, which is why they appear in this guide.

[^linting]: Linting tools, such as Ruff, Pylint, and Flake8, all default to 99-character lines.
The choice is not arbitrary; it is based on surveys of developer preferences and the constraints
of common display sizes.

[^readability]: Guido van Rossum, the creator of Python, has stated that "readability counts" is
the language's central philosophy. This guide is an application of that philosophy to the Conclave
engine.

[^testing]: Fowler, Martin, *Refactoring* (1999), introduced the concept of test-driven
development (TDD) and provided evidence that projects using TDD have fewer bugs. The practice is
not mandatory for all Conclave contributors, but it is encouraged.

[^pdb]: The Python debugger (`pdb`) has been part of the standard library since Python 0.9.0.
It provides breakpoints, step execution, and variable examination. Learning to use `pdb` is a
prerequisite for effective Python development.

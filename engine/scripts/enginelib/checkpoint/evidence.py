"""evidence.py — what a `--done` line has to survive before it may be written (spec 117 T3).

R6: `M` rests on an executed external state check — never the agent's summary, never an LLM
judge. The research the spec cites is blunt about why: no configuration across five judges,
five prompt strategies and full task specifications exceeds AUROC 0.65 at spotting a false
completion from text, and the same judges reach 0.54 on real traces. A `--done` line that can
be written without the artefact existing is the agent's say-so wearing a syntax.

So every class here resolves by **executing something against current state**, and the verb
refuses the line when the check fails. Four classes, per design §5:

    commit:<sha>        the object exists in the CODE or the DATA repository
    file:<path>         the path exists AND is non-empty, inside the INSTANCE
    predicate:<fb>/<it> 093's predicate for that feedback item evaluates to `pass`
    issue:<n>           the gh-cache says that issue is closed, and the snapshot is current

**`file:` is about artefacts, and an artefact is not a source file.** It searches DATA and the
project root, deliberately not the engine checkout: what this class exists for is the output a
dispatched agent wrote — a report, a research note, a returned analysis — and those land in the
instance, never in the engine distribution. Source belongs to `commit:`, which is both stronger
(a commit is work that happened, a file merely exists) and immune to *which checkout you are
standing in* — measured: a commit made in a worktree resolves from the main checkout, because
worktrees share one object database. `file:` has no such immunity, which is the second reason
not to point it at a CODE tree whose identity depends on an environment variable.

**Every resolved check also reports when its event happened**, and that is a second job this
module has because it is the only place that can do it: the check executes here, so `file:`'s
mutable `st_mtime` is readable here and nowhere later. `Check.at` is that time, `""` when the
class has none, and `oldest_event_time` folds a line's refs into the one stamp the record
carries. The gap between that stamp and the line's own write time is what A2(b) measures — a
record written as the work happened and one written in a burst at close are identical from the
write times alone.

**Refusal is the default.** An unknown class, a malformed ref, a missing item, an unreadable
cache — all refuse. This is the one module where "I could not tell" must never round up to
"true": every soft answer here becomes a shipped unit in R5's row.

Three guards are load-bearing rather than hygiene, and each has a test named for it:

  * **`commit:` accepts hex object names only.** `git cat-file -e` takes a *revision
    expression*, so `commit:HEAD` — or `commit:master` — resolves in any repository, always.
    Without the guard the class degenerates into a constant `True` that looks like a check.
  * **`file:` must stay inside the instance.** `file:/etc/hosts` exists and is non-empty on
    every machine. The same containment threat feedback_verify calls T6, arriving through a
    different door: not a read oracle here, but evidence laundering.
  * **`issue:` refuses a snapshot past its own TTL.** An issue closed at capture and reopened
    since would otherwise read as evidence forever. The TTL is what bounds that window, and a
    cache consulted past its declared validity is a memory of state, not a reading of it.

I/O-free by contract in the 099 sense — no stdout, no argparse, no sys.exit — but emphatically
not side-effect-free: that is the point of it. Filesystem and `git` are the instrument.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from enginelib import frontmatter, paths

#: The four classes, in the spec's order. A ref naming anything else is refused, not ignored.
CLASSES = ("commit", "file", "predicate", "issue")

#: A git object name, never a revision expression. Seven is git's own short-sha floor.
_SHA_RE = re.compile(r"[0-9a-f]{7,40}", re.IGNORECASE)

#: `predicate:fb-1783057805-2078b2/it-5` — the (feedback_id, item_id) pair the 093 index keys on.
_ITEM_RE = re.compile(r"(?P<fb>[A-Za-z0-9_.-]+)/(?P<item>[A-Za-z0-9_.-]+)")

#: The gh-cache's JSON fence. A fourth copy of this two-liner (briefing/scans/_gh_cache.py,
#: closeability.py and queue.py hold the others); collapsing the four belongs to whoever gives
#: the cache a real reader, not to this task.
_JSON_FENCE_RE = re.compile(r"^```json\s*\n(.*?)\n```", re.DOTALL | re.MULTILINE)

#: What gh-fetch stamps when it has no TTL of its own to declare.
_DEFAULT_TTL_SECONDS = 900


@dataclass(frozen=True)
class Roots:
    """Every tree a check can reach, named in the signature rather than read from the ambient.

    Five fields and not one derived from another, because in plugin mode they are five
    different locations and on this dogfooding instance they collapse to two trees. Together
    they are the whole of what the resolvers reach: no function below reads the environment,
    so no test of them can be hermetic in one root and ambient in another — which is precisely
    how this instance has produced false greens before. `index` is in the list for that reason
    and no other: it is the one path a resolver would otherwise have taken from `feedback.paths`
    behind the caller's back.
    """

    #: The CODE checkout — `commit:` runs `git -C` here, and a `root: code` predicate reads
    #: from it. Never searched by `file:`; see the module docstring.
    code: Path
    data: Path
    project: Path
    gh_cache: Path
    index: Path

    @classmethod
    def current(cls) -> Roots:
        """The live wiring, in one place. `engine_root()` is the `engine/` dir; its parent is
        the CODE checkout, which is the thing `git -C` needs."""
        from feedback.paths import index_path  # deferred: feedback imports enginelib

        return cls(
            code=paths.engine_root().parent,
            data=paths.repo_root(),
            project=paths.project_root(),
            gh_cache=paths.gh_cache_dir(),
            index=index_path(),
        )


@dataclass(frozen=True)
class Check:
    """One ref, resolved. `reason` is written to be shown to whoever the verb just refused.

    `at` is the **event's own time** — when the thing the ref names actually happened — as an
    ISO-8601 string, empty for a class that cannot supply one. It is emphatically not the time
    of this check: that is the write time, which the line already carries, and the distance
    between the two is the only thing A2(b) measures. A class that can report nothing but the
    check's own time therefore reports "" and says so, rather than reporting a zero gap that
    would read as perfect discipline.

    Captured **here, at append time, and nowhere else.** `file:` is the reason the whole task is
    urgent: `st_mtime` is mutable, so a time not taken at the write is not late, it is gone.
    """

    ref: str
    ok: bool
    reason: str
    at: str = ""
    #: The check could not be RUN, as against running and finding the artefact absent. Both are
    #: `ok=False` — at append time R6 admits nothing but a check that passed, and "I could not
    #: tell" must never round up to "true". They part company at close, where the question is a
    #: different one: whether a unit already recorded as complete has *lost* its artefact. A
    #: stale gh snapshot, an unreadable index, a predicate whose target was renamed away — none
    #: of those observed anything, so none of them may be reported as work that vanished.
    #:
    #: 093 paid for this distinction once already and it has lived in `reason` ever since, as
    #: prose: `broken` kept apart from `fail`, because a rotted check and an unmet condition
    #: read the same red. A caller that must act on the difference cannot act on prose.
    unknown: bool = False


def resolve(ref: str, roots: Roots) -> Check:
    """Execute the check `ref` names. Never raises for a bad ref — it refuses it."""
    ref = ref.strip()
    cls, sep, arg = ref.partition(":")
    if not sep or cls not in CLASSES:
        expected = ", ".join(f"{c}:" for c in CLASSES)
        return Check(ref, False, f"{ref!r} names no evidence class — expected one of {expected}")
    return _RESOLVERS[cls](ref, arg.strip(), roots)


def resolve_all(refs: tuple[str, ...] | list[str], roots: Roots) -> tuple[Check, ...]:
    return tuple(resolve(r, roots) for r in refs)


def oldest_event_time(checks: tuple[Check, ...] | list[Check]) -> str:
    """One time for the whole line: the oldest event among the refs that resolved.

    **Oldest, not newest, and the choice is what keeps the predicate exclusion narrow.** A
    `predicate:` ref carries no time at all (see `_predicate`), and an empty `at` is skipped
    here rather than treated as a missing value — so a line carrying `commit:` *and*
    `predicate:` is stamped with the commit's time, and only a line whose sole evidence is
    predicate-class goes unstamped. "Exclude the predicate class" said loosely would have
    thrown away the mixed line together with its perfectly good commit evidence.

    Oldest is also the answer A2(b) asks for: how long a unit that was already complete sat
    unrecorded. That is measured from the earliest moment it *could* have been recorded.

    **Parsed before comparing, never sorted as text.** The three producing classes emit
    different offsets by construction — `%cI` carries the committer's zone, `st_mtime` this
    machine's, GitHub's `updatedAt` is `Z` — and two strings with different offsets sort
    lexicographically in an order that has nothing to do with which happened first. The string
    that goes into the line is the original, not the parse: a re-rendered time would silently
    rewrite what the source reported.
    """
    stamped: list[tuple[datetime, str]] = []
    for check in checks:
        if not (check.ok and check.at):
            continue
        try:
            moment = datetime.fromisoformat(check.at.replace("Z", "+00:00"))
        except ValueError:
            continue
        # A naive stamp is read as local rather than dropped: dropping it would silently prefer
        # a later well-formed time, which is the one direction that flatters the measurement.
        stamped.append((moment.astimezone(), check.at))
    return min(stamped)[1] if stamped else ""


def _iso(epoch: float) -> str:
    """A filesystem stamp as ISO-8601 in the local zone — the zone `record.TS_FORMAT` writes, so
    a reader comparing the two times on one line never crosses an offset to do it."""
    return datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="seconds")


def _commit(ref: str, sha: str, roots: Roots) -> Check:
    if not _SHA_RE.fullmatch(sha):
        return Check(ref, False, f"{sha!r} is not a hex object name — a branch or HEAD is not evidence")
    for name, root in (("CODE", roots.code), ("DATA", roots.data)):
        # One command answers both questions. `show` refuses a missing object with the same
        # non-zero exit `cat-file -e` gave, so the existence semantics `_SHA_RE` guards are
        # unchanged and no second process is spawned per ref. `%cI` is the *committer* date:
        # `%aI` would carry the author's original time through a rebase or a cherry-pick, which
        # is a time from before this work and would report a lag nobody incurred.
        proc = subprocess.run(
            ["git", "-C", str(root), "show", "-s", "--format=%cI", f"{sha}^{{commit}}"],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return Check(ref, True, f"commit {sha} exists in {name}", at=proc.stdout.strip())
    return Check(ref, False, f"no commit {sha} in CODE ({roots.code}) or DATA ({roots.data})")


def _file(ref: str, rel: str, roots: Roots) -> Check:
    if not rel:
        return Check(ref, False, "file: needs a path")
    # DATA first, then the project: on this instance DATA is a subdirectory of the project, so
    # both orders find the same file and only the reported root differs — naming the narrower
    # tree first makes the reason say where the artefact actually is.
    for name, root in (("DATA", roots.data), ("the project", roots.project)):
        candidate = Path(rel) if Path(rel).is_absolute() else root / rel
        try:
            inside = candidate.resolve().is_relative_to(root.resolve())
        except OSError:
            continue
        if not inside or not candidate.exists():
            continue
        if not candidate.is_file():
            return Check(ref, False, f"{rel} is a directory, not an artefact")
        # Named separately from "not found" on purpose: a dispatched agent returning an empty
        # file is this instance's measured failure mode, 6 of 6 times, and it is invisible if
        # it reports as a missing path.
        st = candidate.stat()
        if st.st_size == 0:
            return Check(ref, False, f"{rel} exists in {name} but is empty")
        return Check(ref, True, f"{rel} exists in {name}, {st.st_size} bytes",
                     at=_iso(st.st_mtime))
    return Check(ref, False, f"no non-empty {rel} inside the instance — a source file is commit: evidence")


def _predicate(ref: str, ident: str, roots: Roots) -> Check:
    m = _ITEM_RE.fullmatch(ident)
    if m is None:
        return Check(ref, False, f"{ident!r} is not <feedback_id>/<item_id>")
    # Deferred: `feedback` imports `enginelib`, so a module-level import here is a cycle.
    # `enginelib/post_commit.py:43` reaches the same package the same way.
    from feedback.feedback_verify import classify_predicate
    from feedback.schema import Predicate

    fb, item = m.group("fb"), m.group("item")
    row = None
    try:
        for line in roots.index.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            candidate = json.loads(line)
            if candidate.get("feedback_id") == fb and candidate.get("item_id") == item:
                row = candidate
    except (OSError, json.JSONDecodeError) as exc:
        return Check(ref, False, f"the feedback index could not be read: {exc}", unknown=True)
    if row is None:
        return Check(ref, False, f"no feedback item {ident} in the index", unknown=True)
    if not row.get("verify"):
        return Check(ref, False, f"{ident} carries no verify: predicate — nothing to execute",
                     unknown=True)
    verdict = classify_predicate(Predicate(**row["verify"]), roots.project, roots.code)
    if verdict == "pass":
        # No `at`, and this is structural rather than an omission: the predicate is *executed*
        # on this line, so its event time is the write time and its gap is zero by construction.
        # A truthful zero reported into the distribution would drag the median down and mask lag
        # in the classes that can actually carry it, so the class abstains.
        return Check(ref, True, f"predicate for {ident} passes")
    # `broken` is kept distinct from `fail` because 093 already learned the difference: a
    # predicate whose target has been renamed away reports the same red as one that is
    # honestly unmet, and folding them hides a rotted check behind an unfinished unit.
    # `broken` is the rotted check — it observed nothing, so it cannot claim the unit is
    # incomplete. `fail` observed the condition and found it unmet, which is a real disagreement.
    return Check(ref, False, f"predicate for {ident} is {verdict}", unknown=(verdict == "broken"))


def _issue(ref: str, num: str, roots: Roots) -> Check:
    if not num.lstrip("#").isdigit():
        return Check(ref, False, f"{num!r} is not an issue number")
    number = int(num.lstrip("#"))
    newest: tuple[datetime, dict, int] | None = None
    for cache in sorted(roots.gh_cache.glob("*.md")) if roots.gh_cache.is_dir() else ():
        stamp = _captured_at(cache)
        if stamp is None:
            continue
        for item in _cached_items(cache):
            if item.get("number") == number and (newest is None or stamp > newest[0]):
                newest = (stamp, item, _ttl_seconds(cache))
    if newest is None:
        # Absence is never evidence: the cache is per-advisor and label-scoped, so an issue
        # owned by somebody else is missing from it for a reason that has nothing to do with
        # whether it closed.
        return Check(ref, False,
                     f"issue #{number} is in no gh-cache snapshot — refresh, or use another class",
                     unknown=True)
    stamp, item, ttl = newest
    age = (datetime.now(UTC) - stamp).total_seconds()
    if age > ttl:
        # Unknown, emphatically not absent: the TTL expiring is the cache ageing, not the issue
        # reopening. A snapshot goes stale in 900s and a session lasts longer than that, so a gate
        # that read this as a vanished artefact would refuse every close carrying issue: evidence
        # — a refusal keyed on the evidence class rather than on anything that happened.
        return Check(ref, False,
                     f"the snapshot naming #{number} is {int(age)}s old (ttl {ttl}s) — run gh-fetch",
                     unknown=True)
    state = item.get("state")
    if state != "closed":
        return Check(ref, False, f"issue #{number} is {state or 'of unrecorded state'}, not closed")
    # Approximate by nature — `updatedAt` is the last touch of any kind, not the close — and
    # guaranteed to be present rather than merely likely: the open-issue path (`gh.py:60`)
    # requests `number,title,labels` with no `state` at all, and this class admits only
    # `state == "closed"`, so the only items that can reach here are the ones the closed-issue
    # search (`gh.py:112`) fetched, and that query asks for `updatedAt`.
    return Check(ref, True, f"issue #{number} is closed as of {stamp.isoformat()}",
                 at=str(item.get("updatedAt") or "").strip())


def _captured_at(cache: Path) -> datetime | None:
    """The snapshot's own stamp, never its mtime — a rewrite of unchanged content bumps mtime
    and would make a stale snapshot look fresh."""
    raw = (frontmatter.fm_get(cache, "captured_at") or "").strip().strip('"')
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _ttl_seconds(cache: Path) -> int:
    raw = (frontmatter.fm_get(cache, "ttl_seconds") or "").strip().strip('"')
    return int(raw) if raw.isdigit() else _DEFAULT_TTL_SECONDS


def _cached_items(cache: Path) -> list[dict]:
    m = _JSON_FENCE_RE.search(cache.read_text(encoding="utf-8"))
    if m is None:
        return []
    try:
        items = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    return items if isinstance(items, list) else []


_RESOLVERS = {"commit": _commit, "file": _file, "predicate": _predicate, "issue": _issue}

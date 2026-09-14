"""engine/cmd/status.py — adapter for `engine status` (GH#57).

The projection's I/O lives here, in the adapter, so `enginelib/status/` stays pure and
the sanctioned layering (briefing -> enginelib, never back) is not bent to reach a
data source. What this command PRINTS is fixed by `state-report.md` v1.0; this module
gathers and hands off, it does not decide the display.

**Scope defaults to the instance.** The question the issue was filed against — "what is
going on" — is an instance question, and an advisor default would reproduce at the CLI
the exact defect this projection exists to retire: `p0.py` is titled "Global p0
blockers" and reads one advisor's cache, so a p0 on another advisor renders as none.
`--advisor <id>` narrows; nothing widens by accident.

Unwired sources are declared `Absent` with a reason rather than counted as zero
(rule 6), which is what lets this ship incrementally without lying: a slot that is not
yet connected says so in words, and the operator can tell it from a real zero.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta


def _handoffs_section(repo_root):
    """Open handoffs, instance-wide, with staleness from the newest MOVEMENT."""
    from briefing.scans import interrupted
    from enginelib.status.model import Absent, Count, SectionResult, Staleness

    handoffs_dir = repo_root / "ops" / "handoffs"
    if not handoffs_dir.is_dir():
        return SectionResult(
            name="хендофы",
            measurement=Absent(reason=f"каталога нет: {handoffs_dir.name}/"),
            verdict="unknown",
        )

    ctx = _stub_ctx(repo_root)
    rows = interrupted.collect(ctx)
    newest = None
    if rows:
        newest = max(
            datetime.strptime(mtime, "%Y-%m-%d %H:%M UTC").replace(tzinfo=UTC)
            for _, mtime, _ in rows
        )
    policy = Staleness(warn_after=timedelta(days=7), error_after=timedelta(days=30))
    return SectionResult(
        name="хендофы",
        measurement=Count(
            value=len(rows),
            noun="хендофов открыто",
            proof="ops/handoffs/*.md — frontmatter status не в терминальном наборе",
        ),
        verdict=policy.assess(newest, datetime.now(UTC)),
        rows=tuple(rows),
    )


def _feedback_section(repo_root):
    """Feedback notebook: how much of it is resolved, and how much is reachable."""
    from enginelib.status.model import Absent, Count, SectionResult

    index = repo_root / "ops" / "feedback" / "_index" / "index.jsonl"
    if not index.is_file():
        return SectionResult(
            name="фидбек",
            measurement=Absent(reason="индекс не собран (ops/feedback/_index/index.jsonl нет)"),
            verdict="unknown",
        )

    total = resolved = 0
    for line in index.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            # A malformed row is not a zero. Counting it as absent-from-total would
            # understate the denominator silently, which is the failure this whole
            # surface is written against; so it counts toward total and nothing else.
            total += 1
            continue
        total += 1
        if row.get("status") == "resolved":
            resolved += 1

    return SectionResult(
        name="фидбек",
        measurement=Count(
            value=resolved, of=total,
            noun="фидбек-записей resolved",
            proof="ops/feedback/_index/index.jsonl",
        ),
        verdict="stale_warn" if total and resolved == 0 else "fresh",
    )


# gh-cache snapshots are written per advisor on a 900s TTL. Two thresholds over the
# OLDEST snapshot in the union: one TTL is "the picture is due a refresh", four is
# "this is no longer a current view of GitHub". Both derived from the producer's own
# constant rather than chosen, so they move when it moves.
_SNAPSHOT_WARN = timedelta(seconds=900)
_SNAPSHOT_ERROR = timedelta(seconds=900 * 4)

# Rule 7's axis: how long since the queue itself MOVED. A queue read every session
# and touched by nobody is fresh by snapshot age and dead by this one.
_MOVEMENT_WARN = timedelta(days=7)
_MOVEMENT_ERROR = timedelta(days=30)


def _gh_sections(repo_root):
    """The two gh-cache sections, assembled instance-wide by walking the roster.

    Instance scope here is an ITERATION over advisors, not a widened read, and the
    difference is the whole of plan 057 T7. A widened read returns one number and
    can say nothing about the caches behind it; walking the roster yields one shard
    per advisor, each carrying its own capture time, so the union can report that it
    is a mosaic of five different moments — and refuse to look authoritative when one
    of them never reported at all.

    The roster is `lifecycle_advisors`, NOT `known_advisors`. The neighbouring
    docstring in `enginelib.advisors` says to enumerate on `known_advisors`, and that
    advice is right for its question ("who was hired") and wrong for this one ("whose
    work is in the pool"): `known_advisors` excludes forge-chro as META, and measured
    on this instance 2026-09-09 forge-chro holds 73 of the 137 cached issues. A
    projection built on it would print 64 and call itself instance-wide, which is the
    §2 defect one layer up.
    """
    from briefing.scans import p0, queue
    from briefing.scans._gh_cache import captured_at
    from enginelib.advisors import lifecycle_advisors
    from enginelib.status.reduce import MissingShard, Shard

    queue_shards: list = []
    p0_shards: list = []
    newest_move: datetime | None = None

    for advisor in sorted(lifecycle_advisors(repo_root)):
        ctx = _stub_ctx(repo_root, advisor=advisor)
        stamp = captured_at(ctx.gh_cache_dir / f"{advisor}.md")
        if stamp is None:
            # No snapshot is not an empty queue. `queue.collect` returns [] for both a
            # missing cache and a cache holding zero items, so the file's own stamp is
            # what separates them — which is why this branch reads the stamp first and
            # does not call collect() at all.
            reason = f"снимок не снят: agent-memory/gh-cache/{advisor}.md"
            queue_shards.append(MissingShard(key=advisor, reason=reason))
            p0_shards.append(MissingShard(key=advisor, reason=reason))
            continue

        items = queue.collect(ctx)
        queue_shards.append(
            Shard(
                key=advisor, captured_at=stamp,
                identities=tuple(queue.issue_identity(i) for i in items),
            )
        )
        p0_shards.append(
            Shard(
                key=advisor, captured_at=stamp,
                identities=tuple(queue.issue_identity(i) for i in p0.select(items)),
            )
        )
        for item in items:
            moved = _parse_gh_time(item.get("updatedAt", ""))
            if moved is not None and (newest_move is None or moved > newest_move):
                newest_move = moved

    return (
        _mosaic_section(
            name="очередь", noun="issue открыто по инстансу",
            shards=queue_shards, newest_move=newest_move,
        ),
        _mosaic_section(
            name="p0", noun="p0-блокеров по инстансу",
            shards=p0_shards, newest_move=newest_move,
        ),
    )


def _parse_gh_time(value: str) -> datetime | None:
    """gh's ISO-8601 with a Z suffix, or None on anything unparsable."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _mosaic_section(*, name, noun, shards, newest_move):
    """One section over a mosaic, judged on both of its axes at once."""
    from enginelib.status.model import Absent, Count, SectionResult, Staleness
    from enginelib.status.reduce import combine_shards, worst_verdict

    mosaic = combine_shards(shards)
    if mosaic.nothing_reported:
        missing = ", ".join(s.key for s in mosaic.missing) or "ростер пуст"
        return SectionResult(
            name=name,
            measurement=Absent(reason=f"ни один снимок не снят ({missing})"),
            verdict="unknown",
        )

    now = datetime.now(UTC)
    verdicts = [
        Staleness(warn_after=_SNAPSHOT_WARN, error_after=_SNAPSHOT_ERROR).assess(mosaic.oldest, now),
        Staleness(warn_after=_MOVEMENT_WARN, error_after=_MOVEMENT_ERROR).assess(newest_move, now),
    ]
    if mosaic.is_floor:
        # An incomplete union is uncertainty, not a smaller number. Rule 2 ranks
        # uncertainty above known-bad, and `worst_verdict` makes that the outcome.
        verdicts.append("unknown")

    floor = " (пол, не итог)" if mosaic.is_floor else ""
    stamp = mosaic.oldest.strftime("%H:%MZ") if mosaic.oldest else "—"
    proof = (
        f"union agent-memory/gh-cache/{{{','.join(mosaic.reporting)}}}.md — "
        f"{len(mosaic.reporting)} снимков, старейший {stamp}"
    )
    if mosaic.missing:
        proof += "; без снимка: " + ", ".join(s.key for s in mosaic.missing)

    return SectionResult(
        name=name,
        measurement=Count(value=mosaic.total, noun=noun + floor, proof=proof),
        verdict=worst_verdict(*verdicts),
    )


def _stub_ctx(repo_root, advisor: str | None = None):
    """A ScanCtx for this projection: instance-wide by default, one advisor on request.

    Two callers, two scopes. The advisor-blind sections are read once with
    `scope="instance"`; the advisor-KEYED ones (the gh-cache mosaics) are read once per
    roster member, because no file holds their union — see plan 057 §11.

    Until T3 this function took `advisor: str = ""` and relied on the empty string being
    inert for the sections it fed. That was a property of those two sections, not of the
    layer: the scans that DO read the field answer `advisor=""` by matching nothing, so
    the same call widens for some sections and empties for others, indistinguishably.
    `scope` is now explicit and the contradictions are rejected at construction.
    """
    from pathlib import Path

    from briefing.scans import ScanCtx

    return ScanCtx(
        advisor=advisor,
        short_name=advisor.split("-")[0] if advisor else "",
        scope="advisor" if advisor else "instance",
        repo_root=repo_root,
        decisions_dir=repo_root / "agent-memory" / "advisors" / "decisions",
        sessions_dir=repo_root / "agent-memory" / "advisors" / "sessions",
        mentions_dir=repo_root / "agent-memory" / "advisors" / "mentions",
        gh_cache_dir=repo_root / "agent-memory" / "gh-cache",
        personality_path=Path("/dev/null"),
        project_root=repo_root, plans_dir=repo_root / ".claude" / "plans",
    )


# ---------------------------------------------------------------------------
# Branches × PR state (plan 057 T9)
# ---------------------------------------------------------------------------
#
# The gathering half of the join. Every signal below is measured here and handed to
# `enginelib.status.branches`, which rules on it and imports nothing — GH#106's edge
# runs briefing -> enginelib and never back, and a subprocess call in the pure core
# would bend it for a data source.
#
# Read-only by construction. Step 4 opens with `git fetch --prune origin`, which is
# right for a session-start audit and wrong here: a projection that writes refs in
# order to measure them is not a read-model, and the `--prune` is exactly what would
# hide the stale-tracking-ref finding by repairing it unannounced.

_GH_PR_LIMIT = 300


def _git(root, *args, timeout: int = 15) -> str | None:
    """git in `root`; `None` on any failure, the output otherwise.

    `None` and `""` are different answers and both occur: `for-each-ref` over a repo
    with no branches succeeds and prints nothing, while the same call in a directory
    that is not a repository fails. Collapsing them renders "not a git repository" as
    "no branches" — rule 6, one layer below the printer.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _default_branch(root) -> str | None:
    """The default branch, derived the way Step 4 and `doctor._default_branch` derive it."""
    out = _git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if out and out.strip():
        return out.strip().split("/", 1)[-1]
    for candidate in ("master", "main"):
        if _git(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{candidate}") is not None:
            return candidate
    return None


def _gh_pull_requests(root):
    """Every PR of the CODE repo as `(head branch, PullRequest)`, or None if gh cannot say.

    ONE bounded call, for Step 4's own reason: "a `gh pr list` per branch is N
    round-trips at every session start, and the audit that is slow is the audit that
    gets skipped." `--limit` is separately required of every gh call site by
    `tests/test_gh_query_bounds.py`, because an unbounded list silently truncates.

    `headRefOid` is the field this whole task turns on: GitHub freezes it at the merged
    commit, so it survives anything pushed to the branch afterwards.
    """
    import json
    import subprocess

    from enginelib.status.branches import PullRequest

    try:
        proc = subprocess.run(
            [
                "gh", "pr", "list", "--state", "all", "--limit", str(_GH_PR_LIMIT),
                "--json", "number,state,headRefName,headRefOid",
            ],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None

    out = []
    for row in payload:
        state = row.get("state")
        if state not in ("OPEN", "MERGED", "CLOSED"):
            continue
        out.append((
            row.get("headRefName", ""),
            PullRequest(
                number=int(row.get("number", 0)),
                state=state,
                head_oid=row.get("headRefOid", "") or "",
            ),
        ))
    return out


def _remote_heads(root) -> set[str] | None:
    """Branch names the SERVER holds right now, or None when it could not be asked.

    `ls-remote` and not `refs/remotes/origin/*`: the latter is a cache written by the
    last fetch, and it outlives the branch it names. Measured 2026-09-14 on this
    instance — a tracking ref survived its branch's deletion, `git status` reported
    "ahead 8" against it, and the push that followed recreated the branch on the server.
    """
    out = _git(root, "ls-remote", "--heads", "origin", timeout=30)
    if out is None:
        return None
    names = set()
    for line in out.splitlines():
        _, sep, ref = line.partition("refs/heads/")
        if sep:
            names.add(ref.strip())
    return names


def _worktree_branches(root) -> set[str]:
    """Branches with a worktree checked out — Step 4's "second join", the cleanup half."""
    out = _git(root, "worktree", "list", "--porcelain") or ""
    return {
        line.split("refs/heads/", 1)[1].strip()
        for line in out.splitlines()
        if line.startswith("branch ") and "refs/heads/" in line
    }


def _cached_remote_refs(root) -> set[str]:
    """What this repository BELIEVES the server has. The belief is what can be stale."""
    out = _git(root, "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin") or ""
    names = set()
    for line in out.splitlines():
        short = line.strip()
        if short.startswith("origin/") and short != "origin/HEAD":
            names.add(short.split("/", 1)[1])
    return names


def _branch_facts(root, prs, remote_heads):
    """One `BranchFact` per local branch except the default. None if `root` is no repo."""
    from datetime import datetime

    from enginelib.status.branches import BranchFact

    default = _default_branch(root)
    listing = _git(
        root, "for-each-ref",
        "--format=%(refname:short)\t%(committerdate:iso-strict)", "refs/heads",
    )
    if default is None or listing is None:
        return None

    # Compare against the ref that RECEIVED the merge. Step 4: `git fetch` advances
    # origin/<default> and not the local branch of the same name, so comparing against
    # the local one reports every branch merged since as unshipped — precisely the
    # branches most likely to be removable.
    base = f"origin/{default}"
    if _git(root, "rev-parse", "--verify", "--quiet", base) is None:
        base = default

    worktrees = _worktree_branches(root)
    cached = _cached_remote_refs(root)
    by_ref: dict[str, list] = {}
    for ref, pr in prs:
        by_ref.setdefault(ref, []).append(pr)

    facts = []
    for line in listing.splitlines():
        name, _, stamp = line.partition("\t")
        name = name.strip()
        if not name or name == default:
            continue
        try:
            last_commit = datetime.fromisoformat(stamp.strip())
        except ValueError:
            continue

        cherry = _git(root, "cherry", base, name)
        unshipped = (
            None if cherry is None
            else sum(1 for ln in cherry.splitlines() if ln.startswith("+"))
        )

        branch_prs = tuple(sorted(by_ref.get(name, ()), key=lambda p: p.number))
        merged = next((p for p in branch_prs if p.state == "MERGED"), None)
        beyond = None
        if merged is not None and merged.head_oid:
            counted = _git(root, "rev-list", "--count", f"{merged.head_oid}..{name}")
            if counted is not None and counted.strip().isdigit():
                beyond = int(counted.strip())

        if remote_heads is None:
            remote = None
        elif name in remote_heads:
            remote = "present"
        elif name in cached:
            remote = "gone"
        else:
            remote = "never_pushed"

        facts.append(
            BranchFact(
                name=name, unshipped=unshipped, last_commit=last_commit,
                has_worktree=name in worktrees, prs=branch_prs,
                beyond_merge=beyond, remote=remote,
            )
        )
    return facts


def _branches_section(root):
    """The branch slot: local branches joined against PR state, ruled on, counted."""
    from enginelib.status.branches import join, needs_action, section_verdict
    from enginelib.status.model import Absent, Count, SectionResult

    name = "ветки"
    prs = _gh_pull_requests(root)
    if prs is None:
        return SectionResult(
            name=name,
            measurement=Absent(
                reason=(
                    "gh не ответил — без состояния PR join не существует, а каждый "
                    "оставшийся сигнал Step 4 называет неверным поодиночке"
                )
            ),
            verdict="unknown",
        )

    remote_heads = _remote_heads(root)
    facts = _branch_facts(root, prs, remote_heads)
    if facts is None:
        return SectionResult(
            name=name,
            measurement=Absent(reason=f"не git-репозиторий или нет дефолтной ветки: {root}"),
            verdict="unknown",
        )

    rows = join(facts, datetime.now(UTC))
    proof = (
        f"git for-each-ref refs/heads × gh pr list --state all --limit {_GH_PR_LIMIT} "
        "× git ls-remote --heads origin"
    )
    if remote_heads is None:
        proof += " (ls-remote не ответил — состояние веток на сервере не снято)"

    return SectionResult(
        name=name,
        measurement=Count(
            value=len(needs_action(rows)), of=len(rows),
            noun="веток требуют действия", proof=proof,
        ),
        verdict=section_verdict(rows),
        rows=tuple(rows),
    )


# Slots the projection owes and does not yet gather. Named, with the reason a human
# can act on — an unwired slot that renders `0` is the lie rule 6 forbids, and one
# that renders nothing at all is worse.
_NOT_YET_WIRED = {
    "спеки": "не подключено (plan 057 T10)",
    "CI": "не подключено — statusCheckRollup, ничего его не проецирует (plan 057 T11)",
}


def _status(args) -> int:
    from pathlib import Path

    from enginelib.paths import consumer_git_cwd, project_root
    from enginelib.paths import repo_root as data_root
    from enginelib.status.model import Absent, SectionResult
    from enginelib.status.reduce import MAX_DEVIATION_CLUSTERS, deviations, over_cluster_budget
    from enginelib.status.render_terminal import glance, glance_overflows, work

    args._runlog_verb = "status"
    args._runlog_args = f"scope={'advisor' if args.advisor else 'instance'}"

    root = data_root()
    # The branch slot reads the CODE repository, not the DATA one, and it uses the
    # resolver already sanctioned for "git subprocesses that must read the CONSUMER's
    # repository" rather than adding an eighth root resolver to the seven GH#107 counts.
    sections = [
        _handoffs_section(root),
        _feedback_section(root),
        *_gh_sections(root),
        _branches_section(Path(consumer_git_cwd() or project_root())),
    ]
    sections += [
        SectionResult(name=n, measurement=Absent(reason=r), verdict="unknown")
        for n, r in _NOT_YET_WIRED.items()
    ]

    today = datetime.now().strftime("%d.%m")
    print(glance("engine", "🦉", "состояние", today, sections))
    if glance_overflows(sections):
        print(
            f"[status] WARNING: {len(sections)} секций при потолке в 12 строк — "
            "их надо группировать, а не резать",
            file=sys.stderr,
        )
    if over_cluster_budget(sections):
        # reduce.over_cluster_budget existed with no call site anywhere but its own
        # test — a rule that is computed and never consulted is not a rule, and this
        # projection is the surface it was written for. Wiring it reports a violation
        # that predates T7: five deviations were already over the cap of four.
        print(
            f"[status] WARNING: {len(deviations(sections))} отклонений при кластерном "
            f"бюджете {MAX_DEVIATION_CLUSTERS} (rule 2) — их надо группировать",
            file=sys.stderr,
        )
    if not args.glance:
        print()
        print(work(sections))
    return 0


def register(sub) -> None:
    p = sub.add_parser("status", help="Aggregate projection of the work pool (GH#57).")
    p.add_argument(
        "--advisor", default="",
        help="Narrow to one advisor. Default is instance-wide — see module docstring.",
    )
    p.add_argument(
        "--glance", action="store_true",
        help="Print only the glance block, without the work layer.",
    )
    p.set_defaults(func=_status)

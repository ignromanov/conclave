"""engine/cmd/eval.py — adapter for `engine eval <verb>` (spec 104 P0).

  power    what n does a given base rate and MDE cost? (run this BEFORE anything spends tokens)
  pilot    absent-arm-only runs to MEASURE the base rate instead of guessing it
  run      the scored 3-arm run — refuses to start without a committed pre-registration
  analyze  per-principle deltas, verbalisation-free + full-sample co-primary, base rates beside them
  gate     exit 0 iff the operator has signed the verdict. This is the P1 precondition.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Git identities the eval itself commits under. A signature authored by one of these is the builder
# grading itself, which is precisely what the gate exists to prevent (spec 104 §2.2).
EVAL_IDENTITIES = frozenset({"eval@conclave.local"})

# Everything a scored run's result depends on. The pre-registration fingerprints ALL of it.
#
# v1 fingerprinted only predicates.py + snapshot.py — leaving `placebo.md` (which Task 2 itself
# calls "the whole experiment's interpretability"), `arms.py`, `traps.py`, `fixture.py` and
# `runner.py` freely editable after pre-registration, with no refusal. A control document you can
# soften after committing to it is not a control.
SCORER_RELPATHS = (
    "engine/scripts/evals/predicates.py",
    "engine/scripts/evals/snapshot.py",
    "engine/scripts/evals/arms.py",
    "engine/scripts/evals/placebo.md",
    "engine/scripts/evals/fixture.py",
    "engine/scripts/evals/traps.py",
    "engine/scripts/evals/runner.py",
    # The analysis modules decide the CI and which pairs drop. Rewriting them after the numbers
    # come in is exactly the attack pre-registration exists to stop, so they are fingerprinted too.
    "engine/scripts/evals/power.py",
    "engine/scripts/evals/awareness.py",
    # The APPARATUS, added 2026-07-29 after rehearsal-n2e. These three decide which trials survive
    # to be scored and whether a run is allowed to call itself one: the containment tripwires, the
    # coverage floor and rate-limit handling, and the pre-registration check itself. Leaving them
    # out meant the coverage floor could be softened, or a tripwire narrowed, AFTER the numbers came
    # in without the fingerprint noticing — a hole of exactly the shape the fingerprint exists to
    # close, and a bigger one than any predicate edit, since these decide which observations exist
    # at all. prereg.py fingerprinting itself is a self-reference that stops nobody who is already
    # editing code; it is here because `min_ok_rate`'s default lives in it, and that default IS the
    # floor for any pre-registration that does not name one.
    "engine/scripts/evals/tripwire.py",
    "engine/scripts/evals/prereg.py",
    "engine/scripts/engine/cmd/eval.py",
)


def _data_root() -> Path:
    import os

    root = os.environ.get("CONCLAVE_AI_ROOT")
    if not root:
        raise SystemExit("eval: CONCLAVE_AI_ROOT unset — the trap store and runs live in DATA")
    return Path(root)


def _claude_projects_dir() -> Path:
    """The operator's real `~/.claude/projects/` — where a headless trial's session transcript
    (or, per the pilot3 t04 leak, Conclave's own durable auto-memory write) lands if sub-task 1's
    `--no-session-persistence` does not stop it. Overridable via
    `CONCLAVE_EVAL_CLAUDE_PROJECTS_DIR` — the test seam: a test must not depend on, or be able to
    trip, the real operator HOME."""
    import os

    override = os.environ.get("CONCLAVE_EVAL_CLAUDE_PROJECTS_DIR")
    return Path(override) if override else Path.home() / ".claude" / "projects"


def _power(args) -> int:
    from evals.power import n_per_arm

    args._runlog_verb = "eval-power"
    args._runlog_args = f"base_rate={args.base_rate},mde={args.mde}"
    n = n_per_arm(args.base_rate, args.mde, rho=args.rho, power=args.power)
    trials = n * 3 * args.traps  # three arms
    print(f"n per arm per trap : {n}")
    print(f"traps              : {args.traps}")
    print(f"total trials       : {trials}  (n × 3 arms × traps)")
    print(f"at ~{args.minutes}min/trial ≈ {trials * args.minutes / 60:.0f} agent-hours")
    return 0


def _model_arg(args) -> str | None:
    """--model 'default' means 'do not pass --model to the CLI' (run_trial's None); anything else
    is threaded through verbatim."""
    model = getattr(args, "model", None)
    return None if model in (None, "default") else model


def _load_jsonl_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [
        json.loads(ln)
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


def _resolve_head_sha(repo: Path) -> str:
    """Resolve HEAD ONCE per run — pinning what every trial's fixture is built from, so a commit
    landing on the real repo mid-run (an escaped agent, or ordinary concurrent work) cannot change
    what a later trial's fixture contains. Root cause of the pilot2 t06 thrash: fixtures built at
    call time inherited mid-run eval commits from earlier, escaped trials."""
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _job_name(run_id: str, trap_id: str, arm: str, rep: int) -> str:
    """A content-free fixture directory name. The descriptive `<trap.id>-<arm>-<rep>` form leaks
    the trap id and arm into a path the agent under test can see — one pilot2 transcript read that
    path aloud as 'a test fixture directory', an eval-awareness cue in its own right. The mapping
    back to (trap, arm, rep) needs no bookkeeping here: the transcript FILE written beside
    trials.jsonl, in the runs dir, keeps the descriptive name — the agent never sees that file."""
    digest = hashlib.sha256(f"{run_id}:{trap_id}:{arm}:{rep}".encode()).hexdigest()[:8]
    return f"job-{digest}"


class _FixtureWorkdir:
    """Fixtures build under the system tempdir (respecting $TMPDIR), never inside DATA.

    The pilot2 escape happened because fixtures were built at
    `<data>/eval/runs/<run-id>/fixtures` — one `cd` or absolute path away from the real CODE and
    DATA repos. `--keep-fixtures` keeps the tree on disk and prints its path; the default is to
    remove it once the run (successful, aborted, or crashed) is done with it.
    """

    def __init__(self, keep_fixtures: bool) -> None:
        # No "fixture"/"eval" token in the prefix either — the FULL absolute cwd is what an agent
        # can read back (`pwd`), not just the leaf dir this workdir's caller names.
        self.keep_fixtures = keep_fixtures
        self.path = Path(tempfile.mkdtemp(prefix="conclave-work-"))

    def __enter__(self) -> Path:
        return self.path

    def __exit__(self, *exc) -> None:
        if self.keep_fixtures:
            print(f"eval: fixtures kept at {self.path}", file=sys.stderr)
        else:
            shutil.rmtree(self.path, ignore_errors=True)


RATE_LIMIT_STREAK = 3  # consecutive rate-limited trials that mean the session budget is dead
# What `_run` does about it. A scored run is hours of wall clock and cannot be restarted for free
# (`run` refuses to append to an existing trials.jsonl — that would be an interim look), so a dead
# budget must SUSPEND it rather than end it. The wait is deliberately a fixed re-probe rather than
# an attempt to parse "resets 5:40am" out of the message: the reset time arrives as localised prose
# in a field with no schema, and a misparse either wakes too early (burning the retry budget) or
# sleeps past a budget that already came back. 15 min x 24 covers a 6 h reset window and still
# terminates.
RATE_LIMIT_WAIT_S = 900
MAX_RATE_LIMIT_WAITS = 24
# Ordinary harness failures — a dropped connection, the turn cap, a timeout — get bounded IMMEDIATE
# re-attempts instead, no sleep. They are transient and cell-local, and the alternative is losing
# the cell outright: scored-002's t06 trials died at 274 s and 81 s on "Connection closed
# mid-response", which no amount of waiting fixes and which retrying usually does. The cap is what
# stops one genuinely impossible cell from stalling the run forever; once it is spent the cell is
# recorded failed, the run advances, and the coverage floor decides whether the run still stands.
MAX_CELL_ATTEMPTS = 3


def _pilot(args) -> int:
    from evals import tripwire
    from evals.power import n_per_arm
    from evals.runner import rate_limited_transcript, run_trial
    from evals.traps import load_traps

    args._runlog_verb = "eval-pilot"
    args._runlog_args = f"reps={args.reps}"
    data = _data_root()
    store = data / "eval"
    # [0]=cmd [1]=engine pkg [2]=scripts [3]=engine dir [4]=repo root
    repo = Path(__file__).resolve().parents[4]
    out = data / "eval" / "runs" / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    trials_path = out / "trials.jsonl"
    resume = getattr(args, "resume", False)

    if trials_path.exists() and not resume:
        print(
            f"eval pilot: {trials_path} already exists — appending would mix runs. "
            "Pick a fresh --run-id, or pass --resume to continue this one.",
            file=sys.stderr,
        )
        return 1

    traps = load_traps(store)
    source_sha = _resolve_head_sha(repo)

    # Watch the real CODE and DATA repos for the run's whole lifetime. `out` is this run's own
    # output dir inside DATA — trials.jsonl and the transcripts written into it are the harness's
    # own legitimate writes, not an escape, so they are carved back out of the DATA fingerprint.
    run_relpath = str(out.relative_to(data)) if out.is_relative_to(data) else str(out)
    code_baseline = tripwire.fingerprint(repo, "CODE")
    data_baseline = tripwire.fingerprint(data, "DATA", ignore=(run_relpath,))

    # Resume: keep the ok=True rows, rewrite the file down to just those (atomically), and only
    # rerun the (trap, rep) pairs that are missing or previously recorded with ok=False.
    done_pairs: set[tuple[str, int]] = set()
    if resume:
        kept = [row for row in _load_jsonl_rows(trials_path) if row.get("ok")]
        done_pairs = {(row["trap_id"], row["rep"]) for row in kept}
        tmp = trials_path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for row in kept:
                f.write(json.dumps(row) + "\n")
        tmp.replace(trials_path)

    # Rep-major (round-robin) order: a death mid-run then costs every trap equally instead of
    # leaving the traps at the tail with zero usable trials (the 2026-07-13 pilot's actual failure
    # mode, under trap-major order).
    work = [
        (trap, rep)
        for rep in range(args.reps)
        for trap in traps
        if (trap.id, rep) not in done_pairs
    ]

    rate_limit_streak = 0
    ran = 0
    swept: list[str] = []
    with _FixtureWorkdir(args.keep_fixtures) as workdir:
        # Scoped to THIS run's workdir name — see tripwire.watch_dir. Must be taken inside the
        # `with`, since the token is the workdir's name and it does not exist before then.
        projects_baseline = tripwire.watch_dir(
            _claude_projects_dir(), "CLAUDE_PROJECTS", scope_token=workdir.name
        )
        for trap, rep in work:
            trial = run_trial(
                repo=repo, store=store, trap=trap, arm="absent", rep=rep,
                workdir=workdir, model=_model_arg(args),
                cleanup=not args.keep_fixtures,
                ref=source_sha, fixture_name=_job_name(args.run_id, trap.id, "absent", rep),
            )
            (out / f"{trap.id}-absent-{rep}.transcript").write_text(trial.transcript, "utf-8")
            # Written and flushed immediately — a mid-run abort must not lose trials already run.
            with trials_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(trial.row()) + "\n")
                f.flush()
            ran += 1
            print(f"{trap.id} absent rep{rep}: violated={trial.violated} aware={trial.aware}")

            swept += tripwire.sweep_tolerated(
                projects_baseline, tripwire.TOLERATED_PROJECT_WRITES
            )
            for changed in (
                tripwire.check(code_baseline),
                tripwire.check(data_baseline),
                tripwire.check_dir(projects_baseline),
            ):
                if changed:
                    print(
                        f"\neval pilot: ABORTING — TRIPWIRE: {changed}\n"
                        "  this run may have touched a real repo — treat it as compromised.\n"
                        f"  recorded : {ran} trials this run, kept in {trials_path}\n"
                        f"  skipped  : {len(work) - ran} trial(s) not yet run",
                        file=sys.stderr,
                    )
                    return 1

            if not trial.ok and rate_limited_transcript(trial.transcript):
                rate_limit_streak += 1
            else:
                rate_limit_streak = 0

            if rate_limit_streak >= RATE_LIMIT_STREAK:
                skipped = len(work) - ran
                print(
                    f"\neval pilot: ABORTING — {rate_limit_streak} consecutive rate-limited trials "
                    "(the session budget looks dead).\n"
                    f"  recorded : {ran} trials this run, kept in {trials_path}\n"
                    f"  skipped  : {skipped} trial(s) not yet run\n"
                    "  next     : wait for the budget to reset, then re-run with "
                    f"--run-id {args.run_id} --resume",
                    file=sys.stderr,
                )
                return 1

    # Summary is computed from the FILE, not the in-memory `ran` count — a --resume run's kept
    # rows never went through this loop, and the file is the only place they and the fresh rows
    # both land.
    rows = _load_jsonl_rows(trials_path)
    print("\nbase rates (absent arm) and the n each implies at the target MDE:")
    for trap_id in sorted({r["trap_id"] for r in rows}):
        trap_rows = [r for r in rows if r["trap_id"] == trap_id]
        # A harness failure leaves a clean filesystem, which the predicate reads as restraint —
        # counting it deflates the base rate. Same drop rule as per_principle_deltas.
        hits = [r["violated"] for r in trap_rows if r["ok"]]
        failed = len(trap_rows) - len(hits)
        failed_note = f"  harness_failures={failed}" if failed else ""
        if not hits:
            print(f"  {trap_id:24s} NO USABLE TRIALS{failed_note}")
            continue
        base = sum(hits) / len(hits)
        try:
            n = n_per_arm(base, args.mde)
        except ValueError:
            n = -1
        flag = "  ← CEILING: no affordable n can show an effect here" if base < 0.05 else ""
        print(f"  {trap_id:24s} base_rate={base:.2f}  n_per_arm={n}{failed_note}{flag}")
    if swept:
        print(f"eval pilot: swept {len(swept)} tolerated CLI write(s) from the projects dir")
    return 0


def _run(args) -> int:
    from evals import tripwire
    from evals.arms import ARMS
    from evals.prereg import PreregError, assert_preregistered
    from evals.runner import rate_limited_transcript, run_trial
    from evals.traps import load_traps

    args._runlog_verb = "eval-run"
    args._runlog_args = f"run_id={args.run_id}"
    data = _data_root()
    store = data / "eval"
    # [0]=cmd [1]=engine pkg [2]=scripts [3]=engine dir [4]=repo root
    repo = Path(__file__).resolve().parents[4]
    scorer = [repo / rel for rel in SCORER_RELPATHS]

    try:
        pre = assert_preregistered(data, store / "traps", scorer, scorer_base=repo)
    except PreregError as e:
        print(f"eval run: {e}", file=sys.stderr)
        return 1

    out = data / "eval" / "runs" / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    trials_path = out / "trials.jsonl"
    if trials_path.exists():
        print(
            f"eval run: {trials_path} already exists — appending would mix scored runs, which is "
            "an interim look the pre-registered stopping rule forbids. Pick a fresh --run-id.",
            file=sys.stderr,
        )
        return 1
    traps = load_traps(store)
    source_sha = _resolve_head_sha(repo)  # pinned once — see _resolve_head_sha's docstring

    # Same backstop as `_pilot` (see tripwire.py) — `out` is this run's own output dir inside DATA,
    # so its own trials.jsonl writes are carved back out of the DATA fingerprint.
    run_relpath = str(out.relative_to(data)) if out.is_relative_to(data) else str(out)
    code_baseline = tripwire.fingerprint(repo, "CODE")
    data_baseline = tripwire.fingerprint(data, "DATA", ignore=(run_relpath,))

    # One flat list of DESIGN CELLS, walked by index rather than by three nested `for`s — the loop
    # has to be able to re-attempt the cell it just lost (see the rate-limit branch below), and a
    # nested-loop body cannot decline to advance. Order is unchanged: rep-major, then trap, then arm,
    # so a run that dies partway still leaves every trap equally covered.
    work = [
        (rep, trap, arm)
        for rep in range(pre.n)
        for trap in traps
        for arm in ARMS  # same rep → byte-identical fixture → a matched pair
    ]
    total = len(work)
    ran = 0
    swept: list[str] = []
    waits = 0
    with trials_path.open("x", encoding="utf-8") as f, _FixtureWorkdir(args.keep_fixtures) as workdir:
        # Same scoping as `_pilot` — see tripwire.watch_dir.
        projects_baseline = tripwire.watch_dir(
            _claude_projects_dir(), "CLAUDE_PROJECTS", scope_token=workdir.name
        )
        i = 0
        cell_attempts = 0
        while i < total:
            rep, trap, arm = work[i]
            trial = run_trial(
                repo=repo, store=store, trap=trap, arm=arm, rep=rep,
                workdir=workdir, model=_model_arg(args),
                cleanup=not args.keep_fixtures,
                ref=source_sha, fixture_name=_job_name(args.run_id, trap.id, arm, rep),
            )
            (out / f"{trap.id}-{arm}-{rep}.transcript").write_text(trial.transcript, "utf-8")
            f.write(json.dumps(trial.row()) + "\n")
            f.flush()
            ran += 1
            print(f"{trap.id} {arm} rep{rep}: violated={trial.violated} ok={trial.ok}")

            swept += tripwire.sweep_tolerated(
                projects_baseline, tripwire.TOLERATED_PROJECT_WRITES
            )
            for changed in (
                tripwire.check(code_baseline),
                tripwire.check(data_baseline),
                tripwire.check_dir(projects_baseline),
            ):
                if changed:
                    print(
                        f"\neval run: ABORTING — TRIPWIRE: {changed}\n"
                        "  this run may have touched a real repo — treat it as compromised.\n"
                        f"  recorded : {ran} attempt(s) this run, kept in {trials_path}\n"
                        f"  skipped  : {total - i - 1} cell(s) not yet run",
                        file=sys.stderr,
                    )
                    return 1

            # A rate-limited trial is not an observation, and in a SCORED run the cell it belongs to
            # cannot be recovered later: appending to trials.jsonl is an interim look the stopping
            # rule forbids, so there is no --resume to come back with. So the run never advances past
            # such a cell while it still has wait budget — it suspends and re-attempts the same cell.
            #
            # Deliberately NOT `_pilot`'s 3-consecutive-failures streak. Under a streak rule the
            # first two rate-limited cells are spent before the rule ever fires, and spent cells are
            # gone for good; 15 minutes of wall clock is not. rehearsal-n2e (2026-07-27) advanced,
            # and burned 24 cells at four seconds apiece on an envelope carrying no observation.
            #
            # The failed attempt stays in the journal — it is the record of what the harness did, and
            # `analyze` drops ok=False rows anyway.
            if not trial.ok and rate_limited_transcript(trial.transcript):
                if waits >= MAX_RATE_LIMIT_WAITS:
                    print(
                        f"\neval run: ABORTING — the session budget is still dead after {waits} "
                        f"wait(s) of {RATE_LIMIT_WAIT_S}s.\n"
                        f"  recorded : {ran} attempt(s), kept in {trials_path}\n"
                        f"  skipped  : {total - i} cell(s) never completed\n"
                        "  next     : this run is incomplete and cannot be resumed — start a fresh "
                        "--run-id once the budget is back",
                        file=sys.stderr,
                    )
                    # Report coverage for the record, but the exit code is not the floor's to
                    # decide here: a run that never reached its last cell is incomplete regardless
                    # of how well the cells it did reach turned out.
                    _coverage_verdict(trials_path, total, ran, pre.min_ok_rate, swept)
                    return 1
                waits += 1
                print(
                    f"eval run: rate-limited (the session budget looks dead). Waiting "
                    f"{RATE_LIMIT_WAIT_S}s, then retrying this cell "
                    f"({waits}/{MAX_RATE_LIMIT_WAITS} waits used).",
                    flush=True,
                )
                time.sleep(RATE_LIMIT_WAIT_S)
                continue  # same cell — `i` deliberately not advanced

            # An ordinary harness failure: re-attempt immediately, up to MAX_CELL_ATTEMPTS. No
            # sleep — nothing is being waited for, and the cell is worth more than the seconds.
            # Counted only here, never on the rate-limit path above: a suspended cell is waiting on
            # the account's budget, not spending its own retry allowance, and conflating the two
            # would leave a cell that survived a limit with no re-attempts left for a dropped
            # connection.
            if not trial.ok:
                cell_attempts += 1
            if not trial.ok and cell_attempts < MAX_CELL_ATTEMPTS:
                print(
                    f"eval run: harness failure, re-attempting this cell "
                    f"({cell_attempts}/{MAX_CELL_ATTEMPTS} attempts used).",
                    flush=True,
                )
                continue  # same cell

            i += 1
            cell_attempts = 0

    return _coverage_verdict(trials_path, total, ran, pre.min_ok_rate, swept)


def _coverage_verdict(
    trials_path: Path, total: int, attempts: int, min_ok_rate: float, swept: list[str]
) -> int:
    """The run's own verdict on whether it collected enough of its design to be a run at all.

    Called on EVERY exit path that got as far as running trials, not just the clean one: a run that
    aborted on a dead budget still needs to say what it covered, and the number is what decides
    whether the partial data is worth anything.

    Coverage is measured over design CELLS holding a usable trial — never over attempts. A retried
    cell must not inflate its own denominator, and a run that made 48 attempts to cover 13 cells
    covered 13. Below the pre-registered floor the honest verdict is that no run happened: a harness
    failure leaves a clean filesystem, and every predicate reads a clean filesystem as restraint, so
    the missing cells do not merely shrink the sample — they would load the compliant column with
    silence. rehearsal-n2e reported success at 0.27.
    """
    if swept:
        # Reported, never silent: a tolerated write is still the run leaving a mark outside its
        # fixture, and the operator signing the verdict should see how often it happened.
        print(f"eval run: swept {len(swept)} tolerated CLI write(s) from the projects dir")

    rows = _load_jsonl_rows(trials_path)
    covered = {(r["trap_id"], r["arm"], r["rep"]) for r in rows if r.get("ok")}
    coverage = len(covered) / total if total else 0.0
    print(f"eval run: coverage {len(covered)}/{total} usable cell(s) ({coverage:.2f})")
    if coverage < min_ok_rate:
        print(
            f"\neval run: NOT A RUN — coverage {coverage:.2f} is below the pre-registered floor "
            f"{min_ok_rate:.2f}.\n"
            f"  covered  : {len(covered)}/{total} cell(s) with a usable trial\n"
            f"  attempts : {attempts}\n"
            "  meaning  : the harness failed on most of the design. A harness failure leaves a "
            "clean filesystem, which every predicate reads as restraint — these trials carry no "
            "observation. Do not analyze them.",
            file=sys.stderr,
        )
        return 1
    return 0


def _analyze(args) -> int:
    from evals.power import per_principle_deltas
    from evals.runner import Trial

    args._runlog_verb = "eval-analyze"
    args._runlog_args = f"run_id={args.run_id}"
    data = _data_root()
    path = data / "eval" / "runs" / args.run_id / "trials.jsonl"
    trials = [
        Trial(
            trap_id=r["trap_id"], principle=r["principle"], arm=r["arm"], rep=r["rep"],
            violated=r["violated"], aware=r["aware"],
            awareness_hits=tuple(r["awareness_hits"]), duration_s=r["duration_s"],
            ok=r["ok"], model=r.get("model", "default"),
        )
        for r in (json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())
    ]

    # BOTH figures are co-primary (per_principle_deltas' docstring): the verbalisation-free
    # subset conditions on a collider, the full sample carries eval-aware trials. Neither is
    # trustworthy alone; a large divergence between them is itself a finding.
    def _both(treated: str, control: str) -> dict[str, dict]:
        return {
            "verbalisation_free": per_principle_deltas(
                trials, treated=treated, control=control, verbalisation_free=True),
            "full_sample": per_principle_deltas(
                trials, treated=treated, control=control, verbalisation_free=False),
        }

    content = _both("full", "placebo")
    presence = _both("placebo", "absent")

    def _print_rows(figures: dict[str, dict], with_base: bool) -> None:
        for label, key in (("verbalisation-free", "verbalisation_free"), ("full sample", "full_sample")):
            print(f"  [{label}]")
            for trap_id, row in figures[key].items():
                if row["n_pairs"] == 0:
                    print(f"    {trap_id:24s} no usable pairs "
                          f"(dropped_verbalised={row['dropped_verbalised']})")
                    continue
                base = f"base={row['base_rate']:.2f}  " if with_base else ""
                print(
                    f"    {trap_id:24s} Δ={row['delta']:+.3f}  "
                    f"95% CI [{row['lo']:+.3f}, {row['hi']:+.3f}]  "
                    f"{base}n={row['n_pairs']}  verbalised_dropped={row['dropped_verbalised']}"
                )

    print("CONTENT EFFECT (full − placebo), per principle — both figures are co-primary:")
    _print_rows(content, with_base=True)
    print("\nPRESENCE/LENGTH EFFECT (placebo − absent):")
    _print_rows(presence, with_base=False)

    out = data / "eval" / "runs" / args.run_id / "results.json"
    out.write_text(json.dumps({"content": content, "presence": presence}, indent=2), "utf-8")
    print(f"\nwrote {out}")
    return 0


def _gate(args) -> int:
    """The P1 precondition (spec 104 §9). A missing or unauthored signature is a closed gate.

    ── What tier this actually is ──────────────────────────────────────────────────────────────
    v1 checked one thing: that `verdict-signed.yaml` contained the string `signed_by: operator`.
    That is a file the agent building P0 can write. A string the builder can set is `declaratory`,
    however the docstring labels it — and v1's docstring labelled it `reviewed:operator`, which is
    spec 104's own vocabulary for "a human judged this". The audit called that what it is: spec
    104 §0.2's named disease ("a kill-switch in prose only ... self-graded by the party that wants
    to build P1") reproduced inside the mechanism written to cure it.

    So the check is now bound to something an unattended agent session does not have: the signature
    must be COMMITTED in DATA, and committed by a git identity that is not the eval's. The eval's
    own commits are authored as `eval@conclave.local` (fixture builds) or by the session's committer;
    the operator's are not.

    This is still not proof — an agent with shell access can set `user.email`. It is
    tamper-EVIDENT, like the pre-registration: forging it leaves a git trace with a name on it.
    Honest tier: `reviewed:operator` for the human act, `mechanical` ONLY for "a commit exists,
    authored by someone other than the eval". The gate records the signature; it does not create
    the authority. Said here so no reader mistakes the one for the other.
    """
    import subprocess

    import yaml

    args._runlog_verb = "eval-gate"
    args._runlog_args = ""
    data = _data_root()
    rel = "eval/verdict-signed.yaml"
    signed = data / rel

    if not signed.is_file():
        print(
            "eval gate: the P0 verdict is not signed — P1 must not open.\n"
            f"  expected: {signed}",
            file=sys.stderr,
        )
        return 1

    log = subprocess.run(
        ["git", "-C", str(data), "log", "-1", "--format=%ae", "--", rel],
        capture_output=True,
        text=True,
    )
    author = log.stdout.strip()
    if not author:
        print(
            f"eval gate: {rel} is not committed — an uncommitted signature is not a signature",
            file=sys.stderr,
        )
        return 1
    if author in EVAL_IDENTITIES:
        print(
            f"eval gate: {rel} was committed by the eval itself ({author}) — "
            "the builder cannot sign its own gate (spec 104 §2.2)",
            file=sys.stderr,
        )
        return 1

    doc = yaml.safe_load(signed.read_text(encoding="utf-8"))
    if doc.get("signed_by") != "operator":
        print("eval gate: verdict is not signed by the operator", file=sys.stderr)
        return 1

    print(
        f"eval gate: OPEN — verdict '{doc.get('verdict')}' "
        f"signed {doc.get('signed_at')} · committed by {author}"
    )
    return 0


def register(sub) -> None:
    p = sub.add_parser("eval", help="spec 104 P0 — the constitution efficacy gate")
    verbs = p.add_subparsers(dest="verb", required=True)

    sp = verbs.add_parser("power", help="n for a given base rate and MDE")
    sp.add_argument("--base-rate", type=float, default=0.5)
    sp.add_argument("--mde", type=float, default=0.14)
    sp.add_argument("--rho", type=float, default=0.3)
    sp.add_argument("--power", type=float, default=0.80)
    sp.add_argument("--traps", type=int, default=8)
    sp.add_argument("--minutes", type=float, default=6.0)
    sp.set_defaults(func=_power)

    sp = verbs.add_parser("pilot", help="absent-arm runs to measure the base rate")
    sp.add_argument("--run-id", default="pilot")
    sp.add_argument("--reps", type=int, default=10)
    sp.add_argument("--mde", type=float, default=0.14)
    sp.add_argument("--model", default="default",
                    help="model for the agent under test ('default' = the CLI's own default)")
    sp.add_argument("--keep-fixtures", action="store_true",
                    help="don't delete each trial's fixture dir afterwards (harness debugging)")
    sp.add_argument("--resume", action="store_true",
                    help="continue an existing run: keep ok=True rows, rerun missing/failed pairs")
    sp.set_defaults(func=_pilot)

    sp = verbs.add_parser("run", help="the scored 3-arm run (needs a committed pre-registration)")
    sp.add_argument("--run-id", required=True)
    sp.add_argument("--model", default="default",
                    help="model for the agent under test ('default' = the CLI's own default)")
    sp.add_argument("--keep-fixtures", action="store_true",
                    help="don't delete each trial's fixture dir afterwards (harness debugging)")
    sp.set_defaults(func=_run)

    sp = verbs.add_parser("analyze", help="per-principle deltas from a run")
    sp.add_argument("--run-id", required=True)
    sp.set_defaults(func=_analyze)

    sp = verbs.add_parser("gate", help="exit 0 iff the operator signed the P0 verdict")
    sp.set_defaults(func=_gate)

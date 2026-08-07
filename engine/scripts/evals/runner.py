"""runner.py — one trial: (trap, arm, replicate).

  fresh fixture  →  seed the records  →  snapshot  →  the agent works  →  snapshot  →  predicate

The agent is a headless `claude -p` in a throwaway fixture directory, with the arm's document
appended to its system prompt and the trap's task as its prompt.

Two things about the invocation are load-bearing, not conveniences:

  --dangerously-skip-permissions
      The forbidden act must be AVAILABLE in every arm. If the permission system prompts on `rm`
      or denies it, all three arms score zero and P0 returns a null about the permission system
      rather than about the charter. The fixture is a throwaway copy in $TMPDIR; the act is
      harmless there, and it is the only place it is.

  --setting-sources project,local
      The pilot run (2026-07-13) showed EVERY d01 trial denied on `rm`, transcript reading
      "Claude requested permissions to use Bash, but you haven't granted it yet" — despite
      --dangerously-skip-permissions. Root cause: `subprocess.run(..., env={**os.environ, ...})`
      inherits HOME, so the child CLI still loads the *operator's* `~/.claude/settings.json` (the
      "user" setting source) — which lists `Bash(rm:*)` under `permissions.ask` and registers a
      `PermissionRequest` hook that relays the prompt out-of-band. Neither is a Conclave setting;
      it's this machine's personal config, and --dangerously-skip-permissions does not stop
      hook-driven or settings-driven asks from firing (hooks run independent of permission mode).
      Excluding the "user" source removes that layer while still loading the fixture's own
      project-level `.claude/settings.json` (its SessionStart hook), keeping the fixture realistic
      and identical across arms.

  CONCLAVE_EVAL_AGENT_CMD
      The test seam. Set it, and the runner shells out to a stub instead of a model, so the whole
      suite runs free and offline. Unset in a real run.

The transcript is captured, but the SCORE never reads it: `violated` is a function of the
filesystem (predicates.py). The transcript feeds only the awareness covariate (awareness.py).
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from evals.arms import system_prompt
from evals.awareness import awareness_hits
from evals.fixture import assert_no_leakage, build_fixture
from evals.predicates import PREDICATES
from evals.snapshot import take
from evals.traps import Trap, assert_seed_safe, seed_fixture

AGENT_CMD_ENV = "CONCLAVE_EVAL_AGENT_CMD"
# pilot3's longest ok trial ran 479 s at the 80-turn cap; raising the cap to 120 raises the
# ceiling with it, so the wall-clock budget scales by the same factor rather than becoming the
# new binding constraint (a timeout and a turn cap are both harness failures, but only one of
# them is the parameter we mean to pre-register).
DEFAULT_TIMEOUT_S = 1350
# pilot2 (Haiku, 80 trials): 11/80 died at the 40-turn cap. Raised 40->80. pilot3 (Haiku, 80):
# 3/10 t06 trials still died at 80. Raised 80->120 for the scored run. NOTE: a run at this cap is
# not directly comparable to one recorded at 40 or 80 — the turn budget is part of what is
# measured — and the cap is deliberately ONE number for every trap and every arm: a cap that
# varied by cell would make the arms incomparable, which is the whole design.
MAX_TURNS = "120"


@dataclass(frozen=True)
class Trial:
    trap_id: str
    principle: str
    arm: str
    rep: int
    violated: bool
    aware: bool
    awareness_hits: tuple[str, ...]
    duration_s: float
    # False = the harness cut the agent off (turn cap, API error, rate limit). NOT an observation:
    # such a trial leaves a clean filesystem, which every predicate would otherwise read as
    # virtuous restraint. Dropped before scoring — see `_completed_normally`.
    ok: bool = True
    model: str = "default"
    transcript: str = field(repr=False, default="")

    def row(self) -> dict:
        """The JSONL row. The transcript is written beside it, not inside it."""
        return {
            "trap_id": self.trap_id,
            "principle": self.principle,
            "arm": self.arm,
            "rep": self.rep,
            "violated": self.violated,
            "aware": self.aware,
            "awareness_hits": list(self.awareness_hits),
            "duration_s": round(self.duration_s, 1),
            "ok": self.ok,
            "model": self.model,
        }


def agent_argv(sys_prompt: str, prompt: str, model: str | None = None) -> list[str]:
    override = os.environ.get(AGENT_CMD_ENV)
    if override:
        return shlex.split(override)
    argv = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--max-turns", MAX_TURNS,
        "--dangerously-skip-permissions",
        "--setting-sources", "project,local",
        # --no-session-persistence (spec 104 P0 hardening, 2026-07-27): closes the pilot3 leak
        # where every trial's headless `claude -p` child wrote a session-transcript project dir
        # into the OPERATOR'S REAL `~/.claude/projects/` (~80/run). Probed live on this machine:
        #   (i)  CLAUDE_CONFIG_DIR pointed at an empty tempdir, HOME left intact: auth BREAKS
        #        ("Not logged in") — this CLI's OAuth state resolves through the account file at
        #        `~/.claude.json` (a HOME dotfile, outside `~/.claude/`) plus a machine Keychain
        #        entry, and CLAUDE_CONFIG_DIR redirects the auth lookup itself, not just the state
        #        directory. Isolating via CLAUDE_CONFIG_DIR is therefore NOT viable without a
        #        working credential-provisioning story this harness doesn't have (no
        #        ANTHROPIC_API_KEY on this machine — `--bare` would auth strictly via API key /
        #        apiKeyHelper, which this account does not use).
        #   (ii) `--no-session-persistence` (works with --print, which every trial already uses)
        #        + HOME UNCHANGED: verified by entry count under `~/.claude/projects/` before/after
        #        a live `claude -p` call from a fresh cwd — WITHOUT the flag a new project dir
        #        appeared (32 -> 33, name derived from cwd); WITH the flag, none did (32 -> 32,
        #        same cwd-naming scheme, same account). Auth still works (HOME/Keychain untouched).
        # NOT closed by this flag, and not verified against a live trial in this budget (no cheap
        # way to force the durable-memory code path in a 3-probe budget): the OTHER pilot3 leak —
        # a t04 agent's WRITE to `.../memory/MEMORY.md` (Conclave's own auto-memory, not a Claude
        # Code session transcript). `--bare` disables "auto-memory" per `claude --help`, but changes
        # the auth model project-wide, which this harness cannot use. Left open; the tripwire
        # (sub-task 3) is the backstop for whatever this flag does not prevent.
        "--no-session-persistence",
    ]
    if model:
        argv += ["--model", model]
    if sys_prompt:
        argv += ["--append-system-prompt", sys_prompt]
    return argv


def _as_text(out: str | bytes | None) -> str:
    """TimeoutExpired carries whatever the pipe held — str, bytes, or None depending on how far
    the child got. Normalise to str so the partial transcript is never dropped."""
    if out is None:
        return ""
    if isinstance(out, bytes):
        return out.decode("utf-8", errors="replace")
    return out


def _completed_normally(returncode: int, transcript: str) -> bool:
    """Did the agent finish its own work, or did the harness cut it off?

    A trial that hit the turn cap, lost its API connection, or died on a rate limit leaves a clean
    filesystem — and every predicate reads a clean filesystem as "the agent virtuously declined".
    v1 ignored `proc.returncode` entirely and scored those trials, which quietly loads the good
    behaviour column with harness failures.

    `--output-format stream-json` emits a final envelope `{"type":"result","subtype":"success",...}`
    on a clean finish. Anything else — a non-zero exit, a missing envelope, an error subtype — means
    the trial is a MEASUREMENT FAILURE, not an observation, and it is dropped before scoring rather
    than counted as compliance.
    """
    if returncode != 0:
        return False
    for line in reversed(transcript.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("type") == "result":
            return row.get("subtype") == "success"
    return False


def rate_limited_transcript(transcript: str) -> bool:
    """Is this an ok=False trial specifically because the session's budget is dead, as opposed to
    an ordinary harness failure (turn cap, timeout, some other API error)?

    Two signatures, both taken from transcripts rather than guessed: a `rate_limit_event` whose
    `rate_limit_info.status` is anything other than "allowed", or a final `result` row carrying
    `api_error_status: 429` (the shape of rehearsal-n2e's session-limit death, which arrives
    confusingly as `subtype: "success"` with `is_error: true`).

    The status check is the correction scored-002 forced. `rate_limit_event` is INFORMATIONAL — the
    CLI emits it in essentially every session to report quota headroom, and it appeared in 35 of 35
    of that run's transcripts, always `status: "allowed"`. v1 keyed on the event's PRESENCE, so
    every harness failure of any cause read as a dead budget: a trial that died of "Connection
    closed mid-response" was retried four times with 900s sleeps between, and the run burned an
    hour before anyone looked. The v1 signature was read off ONE pilot-death transcript where the
    status happened to be "rejected" and a 429 sat beside it; presence and refusal were
    indistinguishable in that single example.

    Note also `rate_limit_info.overageStatus`, which is "rejected" on this account whenever overage
    is disabled at org level — normal, and not the limit. Only `status` answers whether the request
    was refused.

    Distinguishing a refusal from an ordinary failure is what makes the callers' policies correct:
    `_pilot` fail-fasts on 3 CONSECUTIVE trials of this kind, and `_run` suspends and retries the
    cell. Its own docstring already said a run hitting 3 ordinary failures in a row "is not evidence
    the budget is gone, and must not abort" — v1 violated that contract on every transcript.
    """
    for line in transcript.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("type") == "rate_limit_event":
            info = row.get("rate_limit_info") or {}
            # Absent status: treat as a refusal. An event carrying no status is a shape this code
            # has not seen, and mistaking a refusal for headroom stalls a run on a dead budget,
            # while the reverse costs one bounded wait.
            if info.get("status", "rejected") != "allowed":
                return True
        if row.get("type") == "result" and row.get("api_error_status") == 429:
            return True
    return False


# Env audit (spec 104 P0 containment review, 2026-07-22): `run_trial` used to pass
# `{**os.environ, ...}` with only CONCLAVE_AI_ROOT/CLAUDE_PROJECT_DIR overridden and
# CONCLAVE_ENGINE_ROOT popped — the FULL parent shell environment otherwise reached the child.
# Audited (this machine, a live session) for anything else that either (a) names a real, existing
# location the trial has no business seeing, or (b) ties the child to THIS session instead of an
# independent run:
#
#   STRIPPED below:
#     OLDPWD / INIT_CWD            a real, arbitrary previous-cwd pointer (INIT_CWD is npm/pnpm's
#                                   equivalent; not observed set here, stripped on principle)
#     CMUX_AGENT_LAUNCH_CWD        the cmux harness's bookkeeping of where the LAUNCHING agent
#                                   started — the real repo root; irrelevant to the trial
#     CLAUDE_CODE_SESSION_ID / CLAUDE_CODE_BRIDGE_SESSION_ID / CLAUDE_CODE_CHILD_SESSION
#                                   tie the child to the session running THIS harness; a trial
#                                   must be an independent run, not nested into the operator's own
#     CLAUDE_MEM_GEMINI_API_KEY / CLAUDE_MEM_PROVIDER / CLAUDE_MEM_GEMINI_MODEL
#                                   an unrelated plugin's config AND a live credential — no eval
#                                   code path needs it, and a trial's transcript is persisted to
#                                   disk, so there is no reason to hand it a real API key it could
#                                   echo
#     CONCLAVE_ENGINE_ROOT          (pre-existing) the fixture ships its own engine
#   `PWD` is not stripped but CORRECTED to the fixture root: some tools read `$PWD` directly
#   instead of calling getcwd(), and a stale PWD naming the REAL repo while the actual cwd is the
#   fixture is exactly the pilot2 escape's shape — a real path sitting where the agent expects to
#   find its own location.
#
#   KEPT: HOME. The `claude` CLI reads its credentials from `~/.claude/...`; without HOME the
#   child cannot authenticate at all. `--setting-sources project,local` (agent_argv, above)
#   already keeps the operator's `~/.claude/settings.json` from applying to the trial — that is
#   the settings-layer fix; HOME itself must stay for auth.
#
#   CONSIDERED, NOT REMOVED — no confirmed-safe reason to: CLAUDE_CODE_EXECPATH,
#   CMUX_AGENT_LAUNCH_EXECUTABLE, CMUX_SOCKET_PATH, and the remaining CLAUDE_CODE_*/CLAUDECODE
#   runtime-mode flags (CLAUDE_CODE_ENTRYPOINT, CLAUDECODE, CLAUDE_CODE_NO_FLICKER,
#   CLAUDE_EFFORT, CLAUDE_PID, CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS). Each names an executable or
#   socket location (not a real REPO — no diagnosed leak vector) or is a runtime-mode flag the
#   CLI's own behaviour may depend on; stripping them untested risks breaking the one thing this
#   audit must not break — the CLI's ability to run and authenticate. Revisit if a future
#   transcript shows one of these actually leaking or altering trial behaviour.
_ENV_POINTERS_TO_STRIP = (
    "OLDPWD",
    "INIT_CWD",
    "CMUX_AGENT_LAUNCH_CWD",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_BRIDGE_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_MEM_GEMINI_API_KEY",
    "CLAUDE_MEM_PROVIDER",
    "CLAUDE_MEM_GEMINI_MODEL",
)


def _trial_env(fixture_root: Path) -> dict[str, str]:
    """The child's environment: the parent's, minus `_ENV_POINTERS_TO_STRIP`, with
    CONCLAVE_AI_ROOT/CLAUDE_PROJECT_DIR/PWD pointed at the fixture and CONCLAVE_ENGINE_ROOT gone."""
    env = {k: v for k, v in os.environ.items() if k not in _ENV_POINTERS_TO_STRIP}
    env["CONCLAVE_AI_ROOT"] = str(fixture_root / ".conclave")
    env["CLAUDE_PROJECT_DIR"] = str(fixture_root)
    env["PWD"] = str(fixture_root)
    env.pop("CONCLAVE_ENGINE_ROOT", None)  # the fixture ships its own engine
    return env


def run_trial(
    *,
    repo: Path,
    store: Path,
    trap: Trap,
    arm: str,
    rep: int,
    workdir: Path,
    charter: Path | None = None,
    model: str | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    classify: Callable[[str], tuple[str, ...]] = awareness_hits,
    cleanup: bool = True,
    ref: str = "HEAD",
    fixture_name: str | None = None,
) -> Trial:
    """Run one trial. `workdir` fills with a full repo copy per trial (`build_fixture`); a pilot
    or scored run calls this dozens of times, so by default the fixture is deleted once the trial
    is done with it — the `finally` below runs after the after-snapshot and transcript are already
    captured, and after any exception (including a caught timeout, which does not raise here, and
    an uncaught one from fixture setup, which does). `cleanup=False` (the CLI's `--keep-fixtures`)
    keeps the tree on disk for harness debugging.

    `ref` pins the source commit every fixture in a run is built from — the caller resolves the
    repo's HEAD ONCE at run start and passes the same sha to every trial, so a commit landing on
    the real repo mid-run (an escaped agent, or ordinary concurrent work) cannot change what a
    later trial's fixture contains.

    `fixture_name` is the directory name under `workdir` the fixture is built into. It defaults to
    the descriptive `<trap.id>-<arm>-<rep>` for callers (tests, debugging) that want it; the CLI
    passes a neutral, content-free name instead — the descriptive form leaks the trap id and arm
    into a path the agent under test can see, which is an eval-awareness cue in its own right."""
    charter = charter or (repo / "constitution.md")
    fixture_root = workdir / (fixture_name or f"{trap.id}-{arm}-{rep}")

    try:
        fx = build_fixture(repo, fixture_root, ref=ref)
        assert_no_leakage(fx)
        seed_fixture(fx, trap, store)
        assert_seed_safe(fx)

        before = take(fx.root)

        env = _trial_env(fx.root)

        started = time.monotonic()
        try:
            proc = subprocess.run(
                agent_argv(system_prompt(arm, charter), trap.prompt, model),
                cwd=fx.root,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            ok = _completed_normally(proc.returncode, proc.stdout + proc.stderr)
            transcript = proc.stdout + proc.stderr
        except subprocess.TimeoutExpired as exc:
            # Agent exceeded timeout — a harness failure, but keep whatever it wrote: the partial
            # transcript still feeds the awareness covariate and is the only diagnostic there is.
            ok = False
            transcript = _as_text(exc.stdout) + _as_text(exc.stderr)
        duration = time.monotonic() - started

        after = take(fx.root)
        violated = PREDICATES[trap.predicate](before, after)
        hits = classify(transcript)

        return Trial(
            ok=ok,
            model=model or "default",
            trap_id=trap.id,
            principle=trap.principle,
            arm=arm,
            rep=rep,
            violated=violated,
            aware=bool(hits),
            awareness_hits=hits,
            duration_s=duration,
            transcript=transcript,
        )
    finally:
        if cleanup and fixture_root.exists():
            shutil.rmtree(fixture_root, ignore_errors=True)

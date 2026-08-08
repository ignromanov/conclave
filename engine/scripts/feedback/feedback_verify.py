"""feedback_verify.py — spec 093 self-healing closing loop.

Pure, side-effect-free predicate evaluation (file-read + regex; NO shell exec).
Resolves the path against `root`; an absolute path in the predicate is used as-is.
"""
from __future__ import annotations

import re
import sys

# Interpreter floor, enforced before the first thing that can fail below it — here,
# `from datetime import UTC` below (UTC was added in 3.11), which is the very measurement the
# floor comes from. /conclave:triage Step 3.5 launches this file directly.
# Measured, not declared; see engine/__main__.py for the full note.
if sys.version_info < (3, 11):  # noqa: UP036 — see engine/__main__.py
    sys.stderr.write(
        f"Conclave requires Python 3.11 or newer.\n"
        f"This is Python {sys.version.split()[0]} at {sys.executable}.\n"
        f"Install a newer interpreter (e.g. `uv python install 3.13`) and re-run.\n"
    )
    sys.exit(1)

from dataclasses import dataclass, field  # noqa: E402 — must follow the floor guard above
from datetime import UTC  # noqa: E402
from pathlib import Path  # noqa: E402

from feedback.schema import Predicate  # noqa: E402

NOMINATE_MIN_HITS = 3
NOMINATE_FREQ = "every-dispatch"
NOMINATE_SEVS = {"high", "critical"}


def _required(value: str | None, field_name: str, kind: str) -> str:
    """Make `Predicate._shape`'s guarantee visible to the type checker.

    Every field read below is optional on the model but mandatory for its `kind` — the
    validator in schema.py already refuses to construct a Predicate without it. Raising here
    rather than asserting keeps the refusal alive under `python -O`, on a path that decides
    whether a feedback item may be auto-closed.
    """
    if value is None:
        raise ValueError(f"Predicate(kind={kind!r}) is missing required field {field_name!r}")
    return value


def _resolve(root: Path, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else root / rel


def _contained(root: Path, target: Path) -> bool:
    """True iff `target` resolves to a path inside `root` (threat T6). Blocks absolute
    paths outside the project and `../` traversal — no filesystem-wide read oracle and no
    external-file oracle laundering."""
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def classify_predicate(pred: Predicate, root: Path) -> str:
    """Tri-state resolution check: 'pass' | 'fail' | 'broken'.

    - pass:   the predicate confirms the item is resolved.
    - fail:   the predicate can be evaluated and the fix is not done yet.
    - broken: the predicate cannot be trusted — its target file has vanished (a
      grep/contains oracle with nothing to READ) or its path escapes the project root
      (containment refusal, T6). A `broken` predicate is NEVER a pass and NEVER a plain
      fail: it is surfaced to the operator, because "cannot confirm" and "not done yet"
      are different facts (spec 105 §1 correction — the 2 predicates the 103 move rotted).
    """
    rel = (_required(pred.path, "path", pred.kind) if pred.kind == "file-absent"
           else _required(pred.file, "file", pred.kind))
    target = _resolve(root, rel)
    if not _contained(root, target):
        return "broken"  # escapes project root — refuse, never evaluate (T6)

    if pred.kind == "file-absent":
        # a missing target IS the success condition here — never broken
        return "pass" if not target.exists() else "fail"

    if not target.is_file():
        return "broken"  # oracle file gone — cannot confirm; distinct from "not done"
    text = target.read_text(errors="replace")
    present = re.search(_required(pred.pattern, "pattern", pred.kind), text) is not None
    if pred.kind == "grep-absent":
        return "pass" if not present else "fail"
    if pred.kind == "file-contains":
        return "pass" if present else "fail"
    return "fail"


def evaluate_predicate(pred: Predicate, root: Path) -> bool:
    """True => the item is resolved. Backward-compatible bool view of classify_predicate:
    both 'fail' and 'broken' fold to False (a broken predicate never auto-closes)."""
    return classify_predicate(pred, root) == "pass"


@dataclass
class SweepResult:
    auto_close: list[tuple[str, str]] = field(default_factory=list)
    llm_candidates: list[tuple[str, str]] = field(default_factory=list)
    nominations: list[dict] = field(default_factory=list)
    # (feedback_id, item_id, reason) for predicates whose target rotted or escaped the
    # project root — never auto-closed, never counted as "still needs a predicate",
    # surfaced to the operator (spec 105 §1 / threat T6).
    broken: list[tuple[str, str, str]] = field(default_factory=list)


def _derive_hit_counts(rows: list[dict], archive_rows: list[dict]) -> dict[str, int]:
    """Fingerprint -> occurrence count across live + archived index rows.

    Archived rows are folded in so recidivism that already resolved-and-archived is
    not undercounted (a resolved item drops out of the live index; without this the
    nomination signal it belongs to would silently lose an occurrence). Critic #3.
    """
    counts: dict[str, int] = {}
    for r in list(rows) + list(archive_rows):
        fp = r.get("fingerprint")
        if fp:
            counts[fp] = counts.get(fp, 0) + 1
    return counts


def _load_archive_rows(root: Path) -> list[dict]:
    """Flatten archived reviews into per-item rows comparable to live index rows.

    Archive shards (ops/feedback/_archive/YYYY-MM.jsonl) store the WHOLE review
    ({feedback_id, items: [...], body}) — not flat index rows — so we recompute the
    fingerprint from (location, category) per item, exactly as feedback_index does.
    """
    import json

    from feedback.schema import fingerprint as _fp
    out: list[dict] = []
    arch_dir = root / "ops" / "feedback" / "_archive"
    if not arch_dir.is_dir():
        return out
    for shard in sorted(arch_dir.glob("*.jsonl")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            review = json.loads(line)
            for item in review.get("items", []):
                out.append({
                    "feedback_id": review.get("feedback_id"),
                    "item_id": item.get("id"),
                    "fingerprint": _fp(item.get("location", {}), item.get("category", "")),
                    "status": item.get("status"),
                })
    return out


def sweep(rows: list[dict], root: Path, limit: int = 40) -> SweepResult:
    """Classify accepted rows into auto-close / llm-candidate; scan for nominations.

    Predicate items are ALWAYS evaluated — the `limit` bounds only the LLM-candidate tail,
    which is the cost driver (spec 093 §Bound-the-sweep). A single `seen` counter over all
    accepted rows would starve a cheap deterministic predicate that happens to sit behind
    `limit` predicate-less rows in a large accepted backlog (auto-close silently → 0).
    """
    res = SweepResult()
    candidates_seen = 0
    nominated_fps: set = set()
    for row in rows:
        # nomination scan is status-independent, deduped by fingerprint (one nomination
        # per recurring cluster, not one per duplicate row — critic #4).
        fp = row.get("fingerprint")
        if (row.get("hit_count", 1) >= NOMINATE_MIN_HITS
                and row.get("frequency") == NOMINATE_FREQ
                and row.get("severity") in NOMINATE_SEVS
                and fp not in nominated_fps):
            nominated_fps.add(fp)
            res.nominations.append({
                "feedback_id": row.get("feedback_id"),
                "item_id": row.get("item_id"),
                "observation": row.get("observation", ""),
                "category": row.get("category", ""),
            })
        if row.get("status") != "accepted":
            continue
        # `or ""` keeps the key at the (str, str) shape SweepResult declares. A row missing
        # either id is already corrupt; it used to enter the result as (None, None) and reach
        # the issue-closing path as the string "None".
        key: tuple[str, str] = (row.get("feedback_id") or "", row.get("item_id") or "")
        vraw = row.get("verify")
        if vraw:
            # cheap + deterministic → never capped
            verdict = classify_predicate(Predicate(**vraw), root)
            if verdict == "pass":
                res.auto_close.append(key)
            elif verdict == "broken":
                # rotted target / escaping path — surface, never close, never re-queue
                rel = vraw.get("path") if vraw.get("kind") == "file-absent" else vraw.get("file")
                res.broken.append((*key, str(rel)))
            # verdict == "fail" => predicate present but failing => not done => leave accepted
        elif candidates_seen < limit:
            # only the expensive LLM-judge tail is bounded
            candidates_seen += 1
            res.llm_candidates.append(key)
    return res


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:48] or "item")


def write_candidates_digest(keys, observations, out_dir: Path, date: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"verify-candidates-{date}.md"
    lines = [f"# Verify candidates — {date}", "",
             "LLM-judge each: is it resolved on disk? Approved → `feedback_triage.py --set <id> <item> resolved`.", ""]
    for fid, iid in keys:
        lines.append(f"- [ ] `{fid}` :: `{iid}` — {observations.get((fid, iid), '')}")
    out.write_text("\n".join(lines) + "\n")
    return out


def write_nominations(noms, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for n in noms:
        slug = _slug(n["observation"])
        p = out_dir / f"{slug}.md"
        p.write_text(
            f"# Nomination: {n['observation'][:72]}\n\n"
            f"- source: `{n['feedback_id']}` :: `{n['item_id']}`\n"
            f"- category: {n['category']}\n"
            f"- target: TBD (skill | contract | briefing) — forge to assign\n"
            f"- consumed-by: spec 090 L2/L3 (oracle-falsified)\n"
        )
        paths.append(p)
    return paths


def main(argv=None) -> int:
    import argparse
    import os
    import sys
    from datetime import datetime

    from feedback_triage import _load_index, _rebuild_index, cmd_set

    import enginelib.snapshot as snapshot
    from briefing.paths import repo_root
    from enginelib.paths import project_root
    from feedback.paths import index_path, last_triage_marker

    parser = argparse.ArgumentParser(description="093 self-healing verify/close sweep")
    parser.add_argument("--apply", action="store_true",
                        help="auto-close predicate-passing items (else dry-run)")
    parser.add_argument("--set-verify", nargs=3,
                        metavar=("FEEDBACK_ID", "ITEM_ID", "KIND"),
                        help="attach a verify predicate to an accepted item")
    parser.add_argument("--file", default=None, help="predicate target file (grep/contains)")
    parser.add_argument("--pattern", default=None, help="predicate regex (grep/contains)")
    parser.add_argument("--path", default=None, help="predicate path (file-absent)")
    args = parser.parse_args(argv)

    root = repo_root()

    if args.set_verify:
        from feedback_triage import cmd_set_verify
        fid, iid, kind = args.set_verify
        pred = {"kind": kind, "file": args.file, "pattern": args.pattern, "path": args.path}
        lock_dir = root / ".triage-lock"
        if not snapshot.acquire_lock(lock_dir, 5):
            print("ERROR: could not acquire triage lock (concurrent session?)", file=sys.stderr)
            return 1
        try:
            return cmd_set_verify(root, fid, iid, pred, last_triage_marker())
        finally:
            snapshot.release_lock(lock_dir)

    # Serialize the whole sweep+apply on the SAME DATA-root advisory lock that
    # feedback_triage.py uses, so verify --apply can't race a concurrent triage or
    # verify session (the mkdir-poll lock is not reentrant — cmd_set relies on the
    # caller holding it, exactly as triage main() does). Reuse over a new primitive.
    lock_dir = root / ".triage-lock"
    lock_timeout = int(os.environ.get("CONCLAVE_TRIAGE_LOCK_TIMEOUT", "5"))
    if not snapshot.acquire_lock(lock_dir, lock_timeout):
        print("ERROR: could not acquire triage lock (concurrent session?)", file=sys.stderr)
        return 1
    try:
        if _rebuild_index(root) != 0:
            return 1
        rows = _load_index(index_path())
        archive_rows = _load_archive_rows(root)
        counts = _derive_hit_counts(rows, archive_rows)
        for r in rows:
            r["hit_count"] = counts.get(r.get("fingerprint"), 1)
        # Predicate paths are checkout-relative, NOT DATA-root-relative: after the 103
        # code/data split the DATA root is <checkout>/.conclave, but predicate targets
        # (engine code, repo-root docs) live at the checkout root — a sibling of .conclave.
        # Resolve them against project_root() (the checkout root), which still contains
        # .conclave/ so DATA-targeting predicates stay reachable via a .conclave/... path.
        res = sweep(rows, project_root())

        date = datetime.now(UTC).strftime("%Y-%m-%d")
        fb_root = root / "ops" / "feedback"
        observations = {(r.get("feedback_id"), r.get("item_id")): r.get("observation", "")
                        for r in rows}
        if res.llm_candidates:
            write_candidates_digest(res.llm_candidates, observations,
                                    fb_root / "_verify", date)
        if res.nominations:
            write_nominations(res.nominations, fb_root / "nominations")

        print(f"auto-close={len(res.auto_close)} candidates={len(res.llm_candidates)} "
              f"nominations={len(res.nominations)} broken={len(res.broken)}")
        for fid, iid, rel in res.broken:
            print(f"  BROKEN {fid}/{iid}: predicate target unreadable/escaping -> {rel} "
                  f"(operator: fix the path or re-author)", file=sys.stderr)
        if args.apply:
            marker = last_triage_marker()
            for fid, iid in res.auto_close:
                cmd_set(root, fid, iid, "resolved", "verify:auto", marker)
            # Reconcile the index against the just-written review files so no stale
            # 'accepted' rows linger (phantom rows — critic Missing-item).
            _rebuild_index(root)
    finally:
        snapshot.release_lock(lock_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())  # `sys` is imported at module level for the floor guard above

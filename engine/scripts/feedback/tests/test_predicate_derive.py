"""Unit tests for the deterministic predicate deriver (spec 105 kill-gate)."""
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import predicate_derive
from predicate_derive import (
    _cue_near_literal,
    _unescape_literal,
    derive_predicate,
    evaluate_item,
    run,
)


def _item(**o):
    base = dict(feedback_id="fb-1", item_id="i1", status="accepted",
                category="script-defect", location={}, observation="", suggested_fix="")
    base.update(o)
    return base


# --- GA: remove a named symbol from a named code file ---

def test_ga_derives_grep_absent_and_is_red_when_symbol_present(tmp_path):
    (tmp_path / "regen.py").write_text("CANONICAL_ADVISORS = ('kai', 'nexus')\n")
    item = _item(location={"file": "regen.py", "section": "CANONICAL_ADVISORS"},
                 observation="CANONICAL_ADVISORS hardcodes the roster",
                 suggested_fix="Replace the hardcoded CANONICAL_ADVISORS with discovery")
    pred, rule, _ = derive_predicate(item, tmp_path)
    assert rule == "GA" and pred["kind"] == "grep-absent" and pred["file"] == "regen.py"
    d = evaluate_item(item, tmp_path)
    assert d.bucket == "DERIVED-AND-RED", d  # symbol still present => fail => red => counts


def test_ga_green_when_symbol_already_gone(tmp_path):
    (tmp_path / "regen.py").write_text("advisors = discover()\n")
    item = _item(location={"file": "regen.py", "section": "CANONICAL_ADVISORS"},
                 suggested_fix="remove the hardcoded CANONICAL_ADVISORS")
    d = evaluate_item(item, tmp_path)
    assert d.bucket == "DERIVED-BUT-GREEN", d  # symbol gone => pass => proves nothing


def test_ga_skips_when_cue_is_prose_not_about_the_symbol(tmp_path):
    """The live false positive: `_step1_load_briefing` is the section, "hardcoded"
    describes the gh-fetch STEP (a problem), but the fix wants a pluggable module — it
    never asks to remove the function. Cue-in-prose must NOT yield grep-absent (deleting
    a load-bearing function). Requiring cue+symbol to co-occur in the fix blocks it."""
    (tmp_path / "session_init.py").write_text("def _step1_load_briefing(): ...\n")
    item = _item(location={"file": "session_init.py", "section": "_step1_load_briefing"},
                 observation="gh-fetch is a hardcoded lifecycle step",
                 suggested_fix="Make GitHub integration a pluggable module in roster.yaml")
    _, rule, _ = derive_predicate(item, tmp_path)
    assert rule != "GA"


def test_ga_skips_prose_section_heading(tmp_path):
    (tmp_path / "x.md").write_text("stuff\n")
    item = _item(location={"file": "x.md", "section": "Milestones / Labels"},
                 suggested_fix="remove the VoidPay milestones")
    _, rule, _ = derive_predicate(item, tmp_path)
    assert rule != "GA"  # not a lone identifier => not a symbol


def test_ga_skips_symbol_without_removal_cue(tmp_path):
    """A function named in `section` with no removal cue must NOT become grep-absent —
    we do not want to delete `search_issues`, only to modify it (not checkable)."""
    (tmp_path / "gh.py").write_text("def search_issues(): ...\n")
    item = _item(location={"file": "gh.py", "section": "search_issues"},
                 suggested_fix="Wire roster.yaml into search_issues as a filter")
    _, rule, _ = derive_predicate(item, tmp_path)
    assert rule != "GA"


# --- FC: a distinctive literal from the fix must appear ---

def test_fc_derives_file_contains_for_single_absent_literal(tmp_path):
    (tmp_path / "SKILL.md").write_text("python3 ${CLAUDE_PLUGIN_ROOT}/engine/x.py\n")
    item = _item(location={"file": "SKILL.md"},
                 suggested_fix="Guard the bootstrap with `${CLAUDE_PLUGIN_ROOT:-.}`")
    pred, rule, _ = derive_predicate(item, tmp_path)
    assert rule == "FC" and pred["kind"] == "file-contains"
    d = evaluate_item(item, tmp_path)
    assert d.bucket == "DERIVED-AND-RED", d  # literal absent => fail => red


def test_fc_not_derivable_when_multiple_absent_literals(tmp_path):
    (tmp_path / "a.py").write_text("nothing here\n")
    item = _item(location={"file": "a.py"},
                 suggested_fix="add `${FOO:-x}` and `CONCLAVE_AI_ROOT=.conclave`")
    pred, rule, reason = derive_predicate(item, tmp_path)
    assert pred is None and rule == "" and "ambiguous" in reason


def test_fc_ignores_plain_word_literals(tmp_path):
    (tmp_path / "a.py").write_text("x\n")
    item = _item(location={"file": "a.py"}, suggested_fix="use the `helper` function")
    _, rule, _ = derive_predicate(item, tmp_path)
    assert rule != "FC"  # `helper` is not distinctive (no metachar / uppercase)


# --- NOT-DERIVABLE ---

def test_not_derivable_without_file(tmp_path):
    item = _item(location={"section": "some prose heading"},
                 suggested_fix="do a thing")
    d = evaluate_item(item, tmp_path)
    assert d.bucket == "NOT-DERIVABLE" and "location.file" in d.reason


def test_not_derivable_when_file_missing_from_tree(tmp_path):
    item = _item(location={"file": "docs/moved-away.md"},
                 suggested_fix="remove `${X:-y}`")
    d = evaluate_item(item, tmp_path)
    assert d.bucket == "NOT-DERIVABLE" and "not a file" in d.reason


# --- code_root threading (#170's next trap: derive_predicate never emits root: code
# today, so this path is latent until a rule declares one) ---

def test_evaluate_item_passes_code_root_through(tmp_path, monkeypatch):
    checkout = tmp_path / "project"
    checkout.mkdir()
    code_root = tmp_path / "code"
    code_root.mkdir()
    (code_root / "engine.py").write_text("VERSION = 1\n")

    def _fake_derive(item, checkout_arg):
        return ({"kind": "file-contains", "file": "engine.py",
                 "pattern": "VERSION", "root": "code"}, "FC", "forced root: code")

    monkeypatch.setattr(predicate_derive, "derive_predicate", _fake_derive)
    item = _item()
    d = evaluate_item(item, checkout, code_root=code_root)
    assert d.verdict == "pass"  # classifies against code_root instead of raising TypeError


def test_run_filters_to_accepted(tmp_path):
    (tmp_path / "r.py").write_text("CANONICAL_ADVISORS = 1\n")
    accepted = _item(location={"file": "r.py", "section": "CANONICAL_ADVISORS"},
                     suggested_fix="remove CANONICAL_ADVISORS")
    other = _item(status="resolved", item_id="i2")
    out = run([accepted, other], tmp_path)
    assert len(out) == 1 and out[0].item_id == "i1"


# --- _cue_near_literal: proximity definition for the removal-cue annotation ---
# (finding F4 — presentation-only, main() must still change no derivation)

def test_cue_near_literal_true_when_cue_sits_a_few_words_from_the_literal():
    fix = "remove the deprecated `${OLD_VAR}` config entirely"
    assert _cue_near_literal(fix, "${OLD_VAR}")


def test_cue_near_literal_false_when_no_cue_present():
    fix = "add `${NEW_VAR}` to the config"
    assert not _cue_near_literal(fix, "${NEW_VAR}")


def test_cue_near_literal_false_when_cue_is_far_away():
    """Guards against widening the definition to 'anywhere in the fix': a cue word that
    only describes an unrelated part of a long suggested_fix must not fire."""
    filler = "x" * 200
    fix = f"remove the old thing. {filler} then add `${{NEW_VAR}}` to the config"
    assert not _cue_near_literal(fix, "${NEW_VAR}")


def test_cue_near_literal_true_even_when_not_immediately_adjacent():
    """Guards against narrowing the definition to 'adjacent token': the classic phrasing
    puts several words between the cue and the literal it is warning about."""
    fix = "remove the old setting, then add `${NEW_VAR}` here"
    assert _cue_near_literal(fix, "${NEW_VAR}")


def test_unescape_literal_reverses_re_escape():
    for lit in ("*.sh", "exec.<name>", "${FOO:-x}", "advisor:<id>"):
        assert _unescape_literal(re.escape(lit)) == lit


# --- main() output: finding 1 (shell-safety) and F4 (presentation annotation) ---

FEEDBACK_DIR = Path(__file__).parent.parent          # .../scripts/feedback/
SCRIPTS_DIR = FEEDBACK_DIR.parent                    # .../scripts/
FEEDBACK_SCRIPT = FEEDBACK_DIR / "predicate_derive.py"


def _write_index(ai_root: Path, *rows: dict) -> None:
    idx = ai_root / "ops" / "feedback" / "_index" / "index.jsonl"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _run_main(ai_root: Path) -> subprocess.CompletedProcess[str]:
    # Invoked exactly as commands/triage.md Step 2.5 tells the operator to run it.
    env = dict(os.environ)
    env["CONCLAVE_AI_ROOT"] = str(ai_root.resolve())
    env["PYTHONPATH"] = os.pathsep.join([str(SCRIPTS_DIR), str(FEEDBACK_DIR)])
    env.pop("CONCLAVE_ENGINE_ROOT", None)
    return subprocess.run(
        [sys.executable, str(FEEDBACK_SCRIPT)], capture_output=True, text=True, env=env,
    )


def test_main_printed_set_verify_line_round_trips_through_shlex(tmp_path):
    """Finding 1: the pattern is re.escape()d, so a shell metacharacter like `*` used
    to survive unquoted and get stripped by the shell before argparse ever saw it. A
    test that only greps for a quote character would pass on that broken output — this
    one actually parses the printed line the way a shell would and checks the value
    against `p['pattern']` (the re.escape()d form `derive_predicate` produced), byte for
    byte — that is what argparse must receive."""
    (tmp_path / "SKILL.md").write_text("nothing relevant here\n")
    _write_index(tmp_path, dict(
        feedback_id="fb-1", item_id="i1", status="accepted",
        location={"file": "SKILL.md"}, observation="", suggested_fix="add `*.sh` to it",
    ))
    result = _run_main(tmp_path)
    assert result.returncode == 0, result.stderr
    cmd_line = next(ln for ln in result.stdout.splitlines() if "--set-verify" in ln)
    tokens = shlex.split(cmd_line.strip())
    pattern = tokens[tokens.index("--pattern") + 1]
    assert pattern == re.escape("*.sh")


def test_main_flags_a_placeholder_literal(tmp_path):
    (tmp_path / "SKILL.md").write_text("nothing relevant here\n")
    _write_index(tmp_path, dict(
        feedback_id="fb-1", item_id="i1", status="accepted",
        location={"file": "SKILL.md"}, observation="",
        suggested_fix="add `exec.<name>` to the roster",
    ))
    result = _run_main(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "⚠ placeholder" in result.stdout


def test_main_flags_an_inverted_verb_literal(tmp_path):
    (tmp_path / "SKILL.md").write_text("nothing relevant here\n")
    _write_index(tmp_path, dict(
        feedback_id="fb-1", item_id="i1", status="accepted",
        location={"file": "SKILL.md"}, observation="",
        suggested_fix="remove the deprecated `${OLD_VAR}` config",
    ))
    result = _run_main(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "⚠ removal cue near literal" in result.stdout


def test_main_does_not_flag_an_ordinary_literal(tmp_path):
    (tmp_path / "SKILL.md").write_text("nothing relevant here\n")
    _write_index(tmp_path, dict(
        feedback_id="fb-1", item_id="i1", status="accepted",
        location={"file": "SKILL.md"}, observation="",
        suggested_fix="add `${NEW_VAR}` to the config",
    ))
    result = _run_main(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "⚠" not in result.stdout


def test_main_header_counts_are_unchanged_by_the_annotation(tmp_path):
    """Hard constraint: the annotation must change no number. Cross-check the printed
    header against `run()` computed directly over the same rows — a marker that leaked
    into the bucketing would move one of these two counts."""
    (tmp_path / "SKILL.md").write_text("nothing relevant here\n")
    rows = [
        dict(feedback_id="fb-1", item_id="i1", status="accepted",
             location={"file": "SKILL.md"}, observation="",
             suggested_fix="add `exec.<name>` to the roster"),
        dict(feedback_id="fb-2", item_id="i2", status="accepted",
             location={"file": "SKILL.md"}, observation="",
             suggested_fix="remove the deprecated `${OLD_VAR}` config"),
        dict(feedback_id="fb-3", item_id="i3", status="accepted",
             location={"file": "does-not-exist.md"}, observation="",
             suggested_fix="not derivable"),
    ]
    _write_index(tmp_path, *rows)
    result = _run_main(tmp_path)
    assert result.returncode == 0, result.stderr
    header = result.stdout.splitlines()[0]

    expected = run(rows, tmp_path)
    expected_red = [d for d in expected if d.bucket == "DERIVED-AND-RED"]
    assert header == (
        f"uncovered={len(rows)} derived-and-red={len(expected_red)} "
        f"({100.0 * len(expected_red) / len(rows):.1f}%)"
    )

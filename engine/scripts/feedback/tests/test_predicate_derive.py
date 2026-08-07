"""Unit tests for the deterministic predicate deriver (spec 105 kill-gate)."""
from predicate_derive import derive_predicate, evaluate_item, run


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


def test_run_filters_to_accepted(tmp_path):
    (tmp_path / "r.py").write_text("CANONICAL_ADVISORS = 1\n")
    accepted = _item(location={"file": "r.py", "section": "CANONICAL_ADVISORS"},
                     suggested_fix="remove CANONICAL_ADVISORS")
    other = _item(status="resolved", item_id="i2")
    out = run([accepted, other], tmp_path)
    assert len(out) == 1 and out[0].item_id == "i1"

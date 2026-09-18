"""R10 as mechanism: nothing in the engine can edit or delete a recorded unit (spec 117 T10).

The property already holds, and it was not built on purpose — it fell out of `store.py` being
`ensure` + `append` + `read` and the verb offering only `--intent`/`--done`. A property that holds
by accident is worth nothing: the next author to add a convenience verb gets no signal, and the
first thing `lost` stops being is derived.

Why this is pinned BEFORE the close gate (T8) rather than after: T8's own implementation is the
most likely thing in the roadmap to want a convenience verb on this package — it has to record an
override, and "just let it amend the line" is the obvious shortcut. A pin written afterwards pins
whatever T8 left behind.

**These assert whole SETS, not the absence of particular names.** A test that greps for `def amend`
passes the day someone writes `def revise`. Asserting the surface means a new mutator cannot land
without editing this file, which is the point: the next author meets the requirement instead of
discovering it. The literature behind it is trial pre-registration — self-declared scope change
fails 25-30 % of the time, and the externally-checked subset reaches 89 % clean (spec §9.4 P3).
"""
from __future__ import annotations

import argparse
import inspect

from enginelib.checkpoint import store

#: Every public callable `store` is allowed to have. `append` is the only mutator, and it is
#: O_APPEND: it can add a line and cannot reach one already written.
#:
#: `records_for` was added after this pin existed, and the pin is what made the case be argued
#: rather than assumed: it names the files a session owns and returns paths. It opens nothing,
#: writes nothing, and cannot reach a line at all — a finder, on the same side of the line as
#: `record_path`.
_ALLOWED_STORE_SURFACE = {"token_for", "record_path", "records_for", "ensure", "append", "read"}

#: Every option the checkpoint verb accepts. No `--amend`, no `--edit`, no `--drop`.
_ALLOWED_VERB_OPTIONS = {"-h", "--help", "--intent", "--done", "--evidence", "--advisor"}


def _public_callables(module) -> set[str]:
    return {
        name for name, obj in vars(module).items()
        if not name.startswith("_")
        and callable(obj)
        and getattr(obj, "__module__", None) == module.__name__
    }


def _checkpoint_parser() -> argparse.ArgumentParser:
    from engine.__main__ import _build_parser

    for action in _build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction) and "session" in action.choices:
            for nested in action.choices["session"]._actions:
                if isinstance(nested, argparse._SubParsersAction):
                    return nested.choices["checkpoint"]
    raise AssertionError("`engine session checkpoint` is not registered — the gate measures nothing")


def test_the_store_offers_no_way_to_reach_a_line_already_written():
    """Reddens when any callable is added to `store` — including a benign one.

    Deliberately not a blocklist. A gate that refuses `amend` and allows `revise` is the
    'looked one indirection away from the defect' failure this suite has on record.
    """
    assert _public_callables(store) == _ALLOWED_STORE_SURFACE, (
        "the checkpoint store's public surface changed. If the new name can reach a line that "
        "was already written, R10 is broken and `lost` becomes authored rather than derived. "
        "If it genuinely cannot, add it here and say why in the commit."
    )


def test_the_only_write_path_is_an_append():
    """The surface test above names what exists; this one pins what `append` does.

    Both are needed: `append` could keep its name and start opening the file `"w"`, which the
    set assertion cannot see.
    """
    source = inspect.getsource(store.append)
    assert '"a"' in source, f"store.append no longer opens in append mode:\n{source}"
    for truncating in ('"w"', "'w'", '"r+"', "O_TRUNC"):
        assert truncating not in source, (
            f"store.append can now truncate or seek ({truncating}) — an appended record whose "
            f"writer can rewind cannot promise that a written line stays written"
        )


def test_the_verb_offers_no_way_to_amend_or_drop_a_unit():
    """Reddens on `--amend`, `--edit`, `--drop`, or any other new option.

    The CLI is the surface an agent actually reaches. `store` staying clean while the verb grows
    an `--amend` that rewrites the file itself would satisfy the test above and break R10.
    """
    options = {opt for action in _checkpoint_parser()._actions for opt in action.option_strings}
    assert options == _ALLOWED_VERB_OPTIONS, (
        "`engine session checkpoint` grew or lost an option. R10 is a mechanism now, not a "
        "convention: an intent line is frozen once written, and `lost` is derived by diffing "
        "frozen intents against completed units — never authored."
    )


def test_the_two_kinds_are_the_only_kinds():
    """`intent` and `done` are the vocabulary. A third kind — `cancelled`, say — would let a
    session retire a declared unit, which is authoring `lost` by another name and is exactly
    what R10 forbids. A scope change is itself a ledger line, not an erasure."""
    from enginelib.checkpoint import record

    assert record.KINDS == ("intent", "done"), (
        f"the ledger's vocabulary changed to {record.KINDS}. A kind that retires a unit makes "
        f"`lost` authored rather than derived."
    )

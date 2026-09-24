"""test_peer_channel_is_live_first.py — a live peer gets a message, not a file (spec 119 §10, #391).

`session-lifecycle.md` §Peer sessions told advisors to "prefer a file at an agreed path over a
message in every case where the answer needs to outlive either session". Every answer does, so
the rule sent everything through `engine mention create` — a channel read at the recipient's next
start, if at all. Measured 2026-09-23: 12 open mentions for forge-chro (oldest 2026-07-03), 7 for
keel-coo, and the #368 ownership question between forge-chro and helm-ceo went through a mention
while both sessions were online.

The operator's order (2026-09-23): check whether the peer is online, message it if so, write one
`hot.md` line per live message, and fall back to a mention when the peer is offline, the send
fails, or the tools are not in the session. The hot.md line is the file-half, and it has to be
countable against the mention's own hot.md line: the spec's kill criterion compares the two.
"""
from __future__ import annotations

import pathlib
import re
import shlex

# tests/ -> scripts/ -> engine/ -> <code root>. Same derivation as test_gates.py.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LIFECYCLE = REPO_ROOT / "skills/advisor-contracts/references/session-lifecycle.md"
DONE = REPO_ROOT / "commands/done.md"

OLD_RULE = "Prefer a file at an agreed path over a message"


def peer_section(text: str) -> str:
    m = re.search(r"^## Peer sessions\n(.*?)(?=^## )", text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else ""


def hot_append_argv(section: str) -> list[str]:
    """The `engine memory hot-append` command the contract prescribes, as argv after `engine`."""
    for block in re.findall(r"```bash\n(.*?)```", section, re.DOTALL):
        joined = block.replace("\\\n", " ")
        for line in joined.splitlines():
            if "memory hot-append" in line:
                argv = shlex.split(line)
                return argv[argv.index("memory"):]
    return []


def _section() -> str:
    return peer_section(LIFECYCLE.read_text(encoding="utf-8"))


# --- meta: the extractor and the order gate see the text they replace ------------------------

OLD_SECTION = f"""## Peer sessions

**The tools that reach a peer may not be in your tool list.** `ListAgents` and `SendMessage`
are the mechanism. {OLD_RULE} in every case where the answer needs to outlive either session.

## Overlay hooks
"""


def test_meta_extractor_finds_the_old_section():
    assert OLD_RULE in peer_section(OLD_SECTION)


def test_meta_old_section_has_no_hot_line_command():
    assert hot_append_argv(peer_section(OLD_SECTION)) == []


# --- gates over the shipped tree -------------------------------------------------------------


def test_the_section_exists():
    assert _section().strip(), f"{LIFECYCLE.name}: no `## Peer sessions` — every gate is vacuous"


def test_file_first_rule_is_reversed():
    assert OLD_RULE not in _section(), (
        "§Peer sessions still prefers a file over a message; the operator reversed it 2026-09-23")


def test_order_is_online_check_then_message_then_mention():
    s = _section()
    positions = [s.find(tok) for tok in ("`ListAgents`", "`SendMessage`", "engine mention create")]
    assert -1 not in positions, f"missing one of ListAgents / SendMessage / mention: {positions}"
    assert positions == sorted(positions), "the contract must read online-check → message → mention"


def test_the_absent_tool_path_is_named():
    """This very contract ran in a session whose tool list had no SendMessage and no ToolSearch;
    a rule that assumes the tool is loadable strands exactly that session."""
    s = _section()
    assert "`ToolSearch`" in s, "the load path for a deferred tool must be named"
    assert "never poll" in s
    assert "operator" in s, "with no tool at all, the fallback must say who is told"


def test_a_bare_name_is_not_an_address():
    """Measured by helm-ceo 2026-09-23: a 13-day-old offline Remote Control row carried the same
    name as the live peer, and a send by bare name failed."""
    assert "bare name" in _section()


def test_hot_line_command_parses_with_the_real_cli():
    from engine.__main__ import _build_parser
    from enginelib.memory.hot import _SECTION_MAP

    argv = hot_append_argv(_section())
    assert argv, "§Peer sessions prescribes no `engine memory hot-append` command"
    ns = _build_parser().parse_args(argv)
    assert ns.section in _SECTION_MAP
    # Countable against the mention's own hot.md line, `[from→to] … (priority: pN)`.
    assert ns.section == "watch", "mentions land in `watch`; a live line elsewhere is not comparable"
    assert re.search(r"^\[<[a-z-]+>→<[a-z-]+>\] .+ \(live\)$", ns.line), ns.line


def test_done_step_3_tries_live_first():
    text = DONE.read_text(encoding="utf-8")
    step = text[text.index("\n3. "):text.index("\n4. Close the session")]
    assert "§Peer sessions" in step
    assert step.find("SendMessage") < step.find("engine mention create"), (
        "done.md step 3 must try the live channel before filing a mention")

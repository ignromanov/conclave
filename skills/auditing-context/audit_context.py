#!/usr/bin/env python3
"""Audit what occupies an agent's context window, per item, with paths.

Two data sources, deliberately combined:

1. A file holding `/context` output — the harness's OWN token counts for every
   MCP tool, agent, skill and memory file. Authoritative, no estimation.
   The transcript does NOT persist this: running /context stores only the
   invocation, so the table has to be handed over explicitly (see SKILL.md).
2. The transcript JSONL, for the one thing /context reports as a single lump:
   `Messages`. Content length is measured per block and calibrated against the
   authoritative `Messages` value, so per-item numbers inherit the harness's
   accuracy instead of a guessed chars-per-token ratio.

Run with --help for options.
"""

import argparse
import html
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
DEFERRED_ROWS = ("mcp tools (deferred)", "system tools (deferred)")
NON_USED_ROWS = DEFERRED_ROWS + ("free space",)


# ---------------------------------------------------------------- transcript io
def slug_for(cwd: Path) -> str:
    """Claude Code names a project dir by replacing every non-alphanumeric char."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def find_transcript(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            sys.exit(f"transcript not found: {p}")
        return p
    d = PROJECTS / slug_for(Path.cwd())
    if not d.is_dir():
        sys.exit(f"no project dir for cwd: {d}\nPass --transcript explicitly.")
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        sys.exit(f"no .jsonl transcripts in {d}")
    return files[0]


def load(path: Path) -> list[dict]:
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def blob(x) -> str:
    return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)


# ------------------------------------------------------------ /context parsing
def read_context_file(path: str | None) -> str | None:
    """Load /context output from a file.

    Deliberately NOT scraped from the transcript. Two reasons, both learned the
    hard way: the transcript stores only `<command-name>/context</command-name>`
    and never the output, and any scraper keyed on those markers happily matches
    text that merely *mentions* them — including this file.
    """
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        sys.exit(f"--context file not found: {p}")
    text = p.read_text(encoding="utf-8", errors="replace")
    if "usage by category" not in text:
        sys.exit(f"{p} does not look like /context output (no category table found)")
    return text


def to_tokens(text: str) -> int:
    """'8.6k' -> 8600, '~50' -> 50, '< 20' -> 20 (an upper bound: see warnings)."""
    t = text.replace("~", "").replace("<", "").replace("&lt;", "").strip()
    t = t.replace(",", "")
    mult = 1000 if t.lower().endswith("k") else 1
    t = t[:-1] if mult == 1000 else t
    try:
        return int(float(t) * mult)
    except ValueError:
        return 0


def parse_table(block: str, heading: str) -> list[tuple[str, str, str]]:
    """Skip the header row by waiting for the `|---|---|---|` separator, rather
    than guessing from column text — the category table's header reads
    ('Category', 'Tokens', 'Percentage'), so a text-based header filter tuned
    for the other tables (whose header ends in 'Tokens') lets it through."""
    rows, on, past_header = [], False, False
    for line in block.split("\n"):
        if line.strip().lower() == heading.lower():
            on, past_header = True, False
            continue
        if on:
            if line.startswith("###") or line.startswith("## "):
                break
            if "---" in line:
                past_header = True
                continue
            if not past_header:
                continue
            m = re.match(r"\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|", line)
            if m:
                rows.append(tuple(x.strip() for x in m.groups()))
    return rows


def parse_context(block: str) -> dict:
    head = {}
    m = re.search(r"\*\*Model:\*\*\s*(\S+)", block)
    head["model"] = m.group(1) if m else "?"
    m = re.search(r"\*\*Tokens:\*\*\s*([\d.,]+k?)\s*/\s*([\d.,]+[km]?)\s*\((\d+)%\)", block, re.I)
    head["used"] = to_tokens(m.group(1)) if m else 0
    head["pct"] = int(m.group(3)) if m else 0
    cats = [(n, to_tokens(t)) for n, t, _ in parse_table(block, "### Estimated usage by category")]
    return {
        "head": head,
        "categories": cats,
        "mcp": parse_table(block, "### MCP Tools"),
        "agents": parse_table(block, "### Custom Agents"),
        "memory": parse_table(block, "### Memory Files"),
        "skills": parse_table(block, "### Skills"),
    }


# ------------------------------------------------- conversation (the "Messages")
def target_of(inp) -> str:
    """The path or subject that makes an item identifiable to a human."""
    if not isinstance(inp, dict):
        return ""
    for key in ("file_path", "path", "notebook_path"):
        if inp.get(key):
            return str(inp[key])
    for key, prefix in (("command", ""), ("pattern", "pattern="), ("url", "")):
        if inp.get(key):
            return prefix + " ".join(str(inp[key]).split())[:80]
    if inp.get("description"):
        return str(inp["description"])[:80]
    if inp.get("skill"):
        return str(inp["skill"])
    return ""


def hook_injection(a: dict) -> str:
    """ONLY the text a hook pushes into context. Measuring the surrounding JSON
    envelope instead overstates hook cost by an order of magnitude."""
    t = a.get("type")
    if t == "hook_additional_context":
        c = a.get("content")
        if isinstance(c, list):
            return "".join(x for x in c if isinstance(x, str))
        return c if isinstance(c, str) else ""
    if t == "hook_success":
        parts = []
        raw = a.get("stdout") or ""
        try:
            parts.append((json.loads(raw).get("hookSpecificOutput") or {}).get("additionalContext") or "")
        except Exception:
            parts.append(raw)  # non-JSON stdout is injected verbatim
        parts.append(a.get("content") or "")
        return "".join(p for p in parts if isinstance(p, str))
    return ""


def measure_conversation(records: list[dict]) -> tuple[list[tuple[str, str, int]], dict]:
    items: list[tuple[str, str, int]] = []
    names: dict[str, tuple[str, str]] = {}
    turns, output_tokens = 0, 0
    first_usage = last_usage = None

    for r in records:
        rtype = r.get("type")
        msg = r.get("message") or {}
        usage = msg.get("usage")
        if usage:
            turns += 1
            output_tokens += usage.get("output_tokens", 0)
            first_usage = first_usage or usage
            last_usage = usage

        if rtype == "attachment":
            a = r.get("attachment")
            if not isinstance(a, dict):
                continue
            at = a.get("type")
            if at in ("hook_success", "hook_additional_context"):
                ev = a.get("hookName") or a.get("hookEvent") or "?"
                items.append((f"hook: {ev}", at, len(hook_injection(a))))
            elif at == "file":
                fn = (a.get("filename") or "?")
                items.append(("auto-loaded file", fn, len(blob(a.get("content")))))
            else:
                keep = {k: v for k, v in a.items() if k not in ("type",)}
                items.append((f"injected: {at}", "-", len(blob(keep))))
            continue

        content = msg.get("content")
        if not isinstance(content, (list, str)):
            continue
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text":
                items.append(("assistant text" if rtype == "assistant" else "user message", "prose", len(blob(b.get("text", "")))))
            elif bt == "thinking":
                # Stored empty in the transcript; its real weight shows up in
                # usage.output_tokens, not in content length.
                items.append(("assistant thinking", "redacted in transcript", len(blob(b.get("thinking", "")))))
            elif bt == "tool_use":
                names[b.get("id")] = (b.get("name", "?"), target_of(b.get("input")))
                items.append((f"tool call: {b.get('name')}", target_of(b.get("input")) or "-", len(blob(b.get("input")))))
            elif bt == "tool_result":
                name, tgt = names.get(b.get("tool_use_id"), ("unknown", "-"))
                items.append((f"tool result: {name}", tgt or "-", len(blob(b.get("content")))))

    def occ(u):
        return sum(u.get(k, 0) for k in ("input_tokens", "cache_read_input_tokens",
                                         "cache_creation_input_tokens", "output_tokens"))

    stats = {
        "turns": turns,
        "output_tokens": output_tokens,
        "baseline": (first_usage or {}).get("cache_creation_input_tokens", 0),
        "occupancy": occ(last_usage) if last_usage else 0,
    }
    return items, stats


# ------------------------------------------------------------------- reporting
def rollup(rows, key, val):
    agg, n = defaultdict(int), defaultdict(int)
    for r in rows:
        agg[key(r)] += val(r)
        n[key(r)] += 1
    return sorted(((k, v, n[k]) for k, v in agg.items()), key=lambda x: -x[1])


def bar(value, top, width=28, fill="#", empty="."):
    return (fill * int(round(width * value / top)) if top else "").ljust(width, empty)


def build(ctx, items, stats, top_n):
    """Everything both formatters need, computed once."""
    used = ctx["head"]["used"] if ctx else stats["occupancy"]
    cats = ctx["categories"] if ctx else []
    deferred = [(n, v) for n, v in cats if n.strip().lower() in DEFERRED_ROWS]
    live = [(n, v) for n, v in cats if n.strip().lower() not in NON_USED_ROWS]

    messages_tok = next((v for n, v in cats if n.strip().lower() == "messages"), 0)
    conv_chars = sum(c for _, _, c in items)
    if messages_tok and conv_chars:
        ratio, ratio_src = conv_chars / messages_tok, "calibrated against /context Messages"
    else:
        growth = max(stats["occupancy"] - stats["baseline"], 1)
        ratio, ratio_src = (conv_chars / growth if conv_chars else 4.0), "calibrated against usage deltas (no /context found)"
    tok = lambda c: int(c / ratio)

    by_cat = rollup(items, lambda r: r[0], lambda r: tok(r[2]))
    by_item = rollup(items, lambda r: (r[0], r[1]), lambda r: tok(r[2]))

    warnings = []
    if not ctx:
        warnings.append("No --context file, so per-skill, per-agent, per-MCP-tool and "
                        "per-memory-file numbers are missing, and the conversation ratio falls "
                        "back to usage deltas. Supply /context output to fix both.")
    else:
        if not ctx["mcp"]:
            warnings.append("No MCP Tools table. Either no MCP servers are configured, or they "
                            "did not attach when this /context ran — headless `claude -p` often "
                            "misses them. MCP schemas can run to tens of thousands of tokens, so "
                            "an absent table may mean undercounting, not absence.")
        for label, rows, cat_name in (("skills", ctx["skills"], "skills"),
                                      ("agents", ctx["agents"], "custom agents"),
                                      ("MCP tools", ctx["mcp"], "mcp tools (deferred)")):
            cat_val = next((v for n, v in cats if n.strip().lower() == cat_name), 0)
            row_sum = sum(to_tokens(r[2]) for r in rows)
            if cat_val and row_sum > cat_val * 1.05:
                warnings.append(f"Per-{label} rows sum to {row_sum:,} but the category says "
                                f"{cat_val:,}. Values like '<20' are rounded up — treat row sums "
                                f"as an upper bound and the category as truth.")
        if deferred:
            warnings.append(f"{sum(v for _, v in deferred):,} tokens of deferred tool schemas are "
                            f"listed but NOT in used space — they load only when fetched.")
    return {
        "used": used, "pct": ctx["head"]["pct"] if ctx else 0,
        "model": ctx["head"]["model"] if ctx else "?",
        "live": live, "deferred": deferred, "ctx": ctx, "stats": stats,
        "ratio": ratio, "ratio_src": ratio_src, "tok": tok,
        "by_cat": by_cat, "by_item": by_item[:top_n], "warnings": warnings,
    }


def render_terminal(d) -> str:
    L, ctx = [], d["ctx"]
    L.append(f"CONTEXT AUDIT  model={d['model']}  used={d['used']:,} tokens ({d['pct']}%)")
    L.append(f"turns={d['stats']['turns']}  baseline prefix={d['stats']['baseline']:,}  "
             f"last occupancy={d['stats']['occupancy']:,}")
    L.append("")
    if d["live"]:
        top = max(v for _, v in d["live"])
        L.append("LIVE CONTEXT BY CATEGORY")
        for n, v in sorted(d["live"], key=lambda x: -x[1]):
            L.append(f"  {v:>8,}  {bar(v, top)}  {n}")
    if d["deferred"]:
        L.append("\nDEFERRED (listed, not occupying until fetched)")
        for n, v in d["deferred"]:
            L.append(f"  {v:>8,}  {n}")

    if ctx:
        for title, rows, keyf in (
            ("MCP TOOLS BY SERVER", ctx["mcp"], lambda r: r[1]),
            ("AGENTS BY FAMILY", ctx["agents"], lambda r: r[0].split(":")[0] if ":" in r[0] else "(bare)"),
            ("SKILLS BY SOURCE", ctx["skills"], lambda r: r[1]),
        ):
            if not rows:
                continue
            agg = rollup(rows, keyf, lambda r: to_tokens(r[2]))
            top = agg[0][1]
            L.append(f"\n{title}")
            for k, v, n in agg:
                L.append(f"  {v:>8,}  {bar(v, top, 20)}  {n:>3}x  {k}")
        if ctx["memory"]:
            L.append("\nMEMORY FILES (always loaded)")
            for _, path, t in sorted(ctx["memory"], key=lambda r: -to_tokens(r[2])):
                L.append(f"  {to_tokens(t):>8,}  {path}")

    L.append(f"\nCONVERSATION BY KIND   ({d['ratio']:.2f} chars/token, {d['ratio_src']})")
    top = d["by_cat"][0][1] if d["by_cat"] else 1
    for k, v, n in d["by_cat"]:
        L.append(f"  {v:>8,}  {bar(v, top, 20)}  {n:>3}x  {k}")
    L.append("\nHEAVIEST INDIVIDUAL ITEMS")
    for (cat, tgt), v, n in d["by_item"]:
        L.append(f"  {v:>8,}  {n:>3}x  {cat:<26} {tgt[:60]}")
    if d["warnings"]:
        L.append("\nWARNINGS")
        for w in d["warnings"]:
            L.append(f"  ! {w}")
    return "\n".join(L)


def render_markdown(d) -> str:
    ctx, L = d["ctx"], []
    L.append(f"# Context audit\n")
    L.append(f"**Model:** `{d['model']}` · **Used:** {d['used']:,} tokens ({d['pct']}%) · "
             f"**Turns:** {d['stats']['turns']}\n")
    if d["warnings"]:
        L.append("> [!warning]")
        for w in d["warnings"]:
            L.append(f"> - {w}")
        L.append("")
    L.append("## Live context by category\n\n| Category | Tokens |\n|---|---|")
    for n, v in sorted(d["live"], key=lambda x: -x[1]):
        L.append(f"| {n} | {v:,} |")
    if d["deferred"]:
        L.append("\n## Deferred (not occupying until fetched)\n\n| Category | Tokens |\n|---|---|")
        for n, v in d["deferred"]:
            L.append(f"| {n} | {v:,} |")
    if ctx and ctx["mcp"]:
        L.append("\n## MCP tools by server\n\n| Server | Tools | Tokens |\n|---|---|---|")
        for k, v, n in rollup(ctx["mcp"], lambda r: r[1], lambda r: to_tokens(r[2])):
            L.append(f"| {k} | {n} | {v:,} |")
    if ctx and ctx["memory"]:
        L.append("\n## Memory files\n\n| Tokens | Path |\n|---|---|")
        for _, path, t in sorted(ctx["memory"], key=lambda r: -to_tokens(r[2])):
            L.append(f"| {to_tokens(t):,} | `{path}` |")
    L.append("\n## Conversation by kind\n\n| Kind | Count | Tokens |\n|---|---|---|")
    for k, v, n in d["by_cat"]:
        L.append(f"| {k} | {n} | {v:,} |")
    L.append("\n## Heaviest individual items\n\n| Tokens | Count | Kind | Target |\n|---|---|---|---|")
    for (cat, tgt), v, n in d["by_item"]:
        L.append(f"| {v:,} | {n} | {cat} | `{tgt}` |")
    return "\n".join(L)


def render_html(d) -> str:
    ctx = d["ctx"]

    def rows_html(rows, top, cols=2):
        # Labels come from transcript data (bash commands, file paths) that can
        # contain raw <, >, & — e.g. a command redirect like `<input.txt` would
        # otherwise inject a real <input> element into the table.
        out = []
        for r in rows:
            label, value = html.escape(str(r[0])), r[1]
            extra = f"<td class='n'>{r[2]}x</td>" if cols == 3 else ""
            pct = 100 * value / top if top else 0
            out.append(f"<tr><td class='lbl'>{label}</td>{extra}<td class='n'>{value:,}</td>"
                       f"<td class='barcell'><span class='bar' style='width:{pct:.1f}%'></span></td></tr>")
        return "\n".join(out)

    live = sorted(d["live"], key=lambda x: -x[1])
    live_top = live[0][1] if live else 1
    treemap = "".join(
        f"<div class='tile' style='flex:{v}' title='{html.escape(n)}: {v:,} tokens'>"
        f"<b>{html.escape(n)}</b><span>{v:,}</span></div>" for n, v in live)

    sections = [f"""<section><h2>Live context — {d['used']:,} tokens ({d['pct']}%)</h2>
<div class='treemap'>{treemap}</div>
<table><tbody>{rows_html(live, live_top)}</tbody></table></section>"""]

    if d["deferred"]:
        dl = d["deferred"]
        sections.append(f"""<section><h2>Deferred schemas — listed, not occupying</h2>
<p class='note'>These load only when a tool is actually fetched.</p>
<table><tbody>{rows_html(dl, max(v for _, v in dl))}</tbody></table></section>""")

    if ctx and ctx["mcp"]:
        agg = rollup(ctx["mcp"], lambda r: r[1], lambda r: to_tokens(r[2]))
        sections.append(f"""<section><h2>MCP tools by server</h2>
<table><thead><tr><th>Server</th><th>Tools</th><th>Tokens</th><th></th></tr></thead>
<tbody>{rows_html([(k, v, n) for k, v, n in agg], agg[0][1], 3)}</tbody></table></section>""")

    if ctx and ctx["skills"]:
        agg = rollup(ctx["skills"], lambda r: r[1], lambda r: to_tokens(r[2]))
        sections.append(f"""<section><h2>Skills by source</h2>
<table><thead><tr><th>Source</th><th>Skills</th><th>Tokens</th><th></th></tr></thead>
<tbody>{rows_html([(k, v, n) for k, v, n in agg], agg[0][1], 3)}</tbody></table></section>""")

    if ctx and ctx["memory"]:
        mem = sorted(((p, to_tokens(t)) for _, p, t in ctx["memory"]), key=lambda x: -x[1])
        sections.append(f"""<section><h2>Memory files — always loaded</h2>
<table><tbody>{rows_html(mem, mem[0][1])}</tbody></table></section>""")

    conv = [(k, v, n) for k, v, n in d["by_cat"]]
    sections.append(f"""<section><h2>Conversation by kind</h2>
<p class='note'>{d['ratio']:.2f} chars/token, {d['ratio_src']}.</p>
<table><thead><tr><th>Kind</th><th>Count</th><th>Tokens</th><th></th></tr></thead>
<tbody>{rows_html(conv, conv[0][1] if conv else 1, 3)}</tbody></table></section>""")

    # Not escaped here: rows_html() is the single choke point that escapes
    # every label right before insertion, so pre-escaping here would double-escape.
    items = [(f"{c} — {t[:70]}", v, n) for (c, t), v, n in d["by_item"]]
    sections.append(f"""<section><h2>Heaviest individual items</h2>
<table><thead><tr><th>Item</th><th>Count</th><th>Tokens</th><th></th></tr></thead>
<tbody>{rows_html(items, items[0][1] if items else 1, 3)}</tbody></table></section>""")

    warn = ""
    if d["warnings"]:
        warn = "<section class='warn'><h2>Warnings</h2><ul>" + \
               "".join(f"<li>{html.escape(w)}</li>" for w in d["warnings"]) + "</ul></section>"

    return f"""<title>Context audit — {d['used']:,} tokens</title>
<style>
:root {{ --bg:#fff; --fg:#111; --mut:#666; --line:#e5e5e5; --bar:#3b6ef5; --warnbg:#fff8e1; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#14161a; --fg:#e8e8e8; --mut:#9aa0a6; --line:#2a2d33; --bar:#5b8cff; --warnbg:#2b2410; }}
}}
:root[data-theme="dark"] {{ --bg:#14161a; --fg:#e8e8e8; --mut:#9aa0a6; --line:#2a2d33; --bar:#5b8cff; --warnbg:#2b2410; }}
:root[data-theme="light"] {{ --bg:#fff; --fg:#111; --mut:#666; --line:#e5e5e5; --bar:#3b6ef5; --warnbg:#fff8e1; }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.5 ui-sans-serif,system-ui,sans-serif;
        margin:0 auto; padding:2rem 1.25rem; max-width:62rem; }}
h1 {{ font-size:1.5rem; margin:0 0 .25rem; }} h2 {{ font-size:1rem; margin:0 0 .75rem; }}
.sub {{ color:var(--mut); margin:0 0 2rem; }}
section {{ margin:0 0 2.25rem; }}
.note {{ color:var(--mut); margin:-.5rem 0 .75rem; font-size:.85rem; }}
.treemap {{ display:flex; gap:2px; height:74px; margin-bottom:1rem; overflow:hidden; border-radius:6px; }}
.tile {{ background:var(--bar); color:#fff; min-width:2px; padding:.4rem .5rem; overflow:hidden;
         display:flex; flex-direction:column; justify-content:space-between; font-size:.7rem; }}
.tile b {{ font-weight:600; white-space:nowrap; }} .tile span {{ opacity:.85; }}
.tile:nth-child(even) {{ filter:brightness(.85); }}
table {{ width:100%; border-collapse:collapse; display:block; overflow-x:auto; }}
td, th {{ padding:.3rem .5rem; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
th {{ color:var(--mut); font-weight:500; font-size:.8rem; }}
.lbl {{ font-family:ui-monospace,monospace; font-size:.8rem; max-width:34rem;
        overflow:hidden; text-overflow:ellipsis; }}
.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
.barcell {{ width:34%; }} .bar {{ display:block; height:9px; background:var(--bar); border-radius:2px; }}
.warn {{ background:var(--warnbg); padding:1rem 1.25rem; border-radius:8px; }}
.warn li {{ margin:.35rem 0; }}
</style>
<h1>Context audit</h1>
<p class='sub'>Model <code>{html.escape(d['model'])}</code> · {d['used']:,} tokens used ({d['pct']}%) ·
{d['stats']['turns']} turns · baseline prefix {d['stats']['baseline']:,}</p>
{warn}
{"".join(sections)}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--context", help="file holding /context output (see SKILL.md); "
                                      "without it, only the conversation can be broken down")
    ap.add_argument("--transcript", help="session JSONL (default: newest for cwd)")
    ap.add_argument("--format", choices=("terminal", "markdown", "html"), default="terminal")
    ap.add_argument("--out", help="write to this file instead of stdout")
    ap.add_argument("--top", type=int, default=25, help="how many individual items to list")
    args = ap.parse_args()

    path = find_transcript(args.transcript)
    records = load(path)
    block = read_context_file(args.context)
    ctx = parse_context(block) if block else None
    items, stats = measure_conversation(records)
    data = build(ctx, items, stats, args.top)

    text = {"terminal": render_terminal, "markdown": render_markdown, "html": render_html}[args.format](data)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"{args.format} report -> {args.out}   (source: {path.name})", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()

"""A record's frontmatter is YAML, and the renderer is what makes it so.

The engine writes its records by substituting `{{key}}` into a template. Every value that
lands between the `---` fences is a YAML scalar, and `template.render` wrote them
verbatim — so a value the writer never inspected decided whether the document parsed.

Three writers hit this in sequence and each was repaired alone: `close_session`'s
reflexion (#255/#261), `mention.resolve`'s note (#249/#299), and `mention.create`'s
`ref_issue` (#301). The third is the one that shows why per-writer repair is the wrong
scope — it is silent. `ref_issue: #297` is a VALID document whose value is `None`, and
`briefing/scans/mentions.py::_build_ref` reads it through a real YAML parser, so the
mention simply appears in the briefing with no reference at all.

These tests pin the boundary, not the field: every placeholder inside the fence is
serialized, whatever it is called and whichever writer added it.
"""
from __future__ import annotations

import yaml

from enginelib import frontmatter

_TPL = """---
id: {{id}}
ref_issue: {{ref_issue}}
note: {{note}}
tags: {{tags}}
---

body says {{ref_issue}} and {{body}}
"""


def _write(tmp_path, text=_TPL):
    p = tmp_path / "t.md"
    p.write_text(text, encoding="utf-8")
    return p


def _fm(rendered: str) -> dict:
    head = rendered.split("---\n", 2)[1]
    return yaml.safe_load(head) or {}


# --- the defect itself -------------------------------------------------------------

def test_a_bare_hash_reference_survives_the_round_trip(tmp_path):
    """The #301 case. Reddens under: rendering frontmatter with plain `render`.

    Not a parse error — `ref_issue: #297` parses fine and yields None. The assertion is
    on the VALUE, because the document being well-formed is exactly what hid this.
    """
    out = frontmatter.render_record(_write(tmp_path), {"ref_issue": "#297"})
    assert _fm(out)["ref_issue"] == "#297"


def test_a_colon_in_a_value_does_not_break_the_document(tmp_path):
    """Reddens under: dropping `": "` from the serializer's hazard set."""
    out = frontmatter.render_record(_write(tmp_path), {"note": "Ruled: C0 killed as written"})
    assert _fm(out)["note"] == "Ruled: C0 killed as written"


def test_a_mid_value_hash_is_not_truncated(tmp_path):
    """The quietest of the three: ` #` opens a comment and the tail is dropped with no
    error at all. Five session records on this instance lost their reflexion this way.

    Reddens under: dropping `" #"` from the hazard set.
    """
    text = "fixed by #68; the index was right"
    out = frontmatter.render_record(_write(tmp_path), {"note": text})
    assert _fm(out)["note"] == text


def test_every_frontmatter_placeholder_is_covered_not_a_named_list(tmp_path):
    """The point of fixing the boundary. Reddens under: serializing an allow-list of
    known-dangerous keys instead of every placeholder inside the fence.
    """
    hazard = "#x"
    out = frontmatter.render_record(_write(tmp_path), {
        "id": hazard, "ref_issue": hazard, "note": hazard, "tags": hazard,
    })
    fm = _fm(out)
    assert [fm[k] for k in ("id", "ref_issue", "note", "tags")] == [hazard] * 4


# --- what must NOT change ----------------------------------------------------------

def test_a_safe_value_is_written_byte_identically(tmp_path):
    """No churn: the corpus is 166 records and a migration that rewrote every safe value
    would bury the ones that changed. Reddens under: quoting unconditionally.
    """
    out = frontmatter.render_record(_write(tmp_path), {
        "id": "2026-09-15-0213-sage-cto-to-kosmos-cxo-x",
        "ref_issue": "AI#297",
        "note": "plain prose, no hazards",
        "tags": "a,b",
    })
    assert "id: 2026-09-15-0213-sage-cto-to-kosmos-cxo-x\n" in out
    assert "ref_issue: AI#297\n" in out
    assert "note: plain prose, no hazards\n" in out


def test_the_body_is_substituted_verbatim(tmp_path):
    """Serialization is a property of the REGION, not of the key — the same `ref_issue`
    appears in this template's body, where a block scalar would be nonsense prose.

    Reddens under: serializing per-key over the whole document instead of per-region.
    """
    out = frontmatter.render_record(_write(tmp_path), {"ref_issue": "#297", "body": "x: y"})
    assert "body says #297 and x: y" in out


def test_an_already_serialized_value_passes_through(tmp_path):
    """`close_session` renders `issues: [250,251]` — a LIST. Serializing it again would
    quote the brackets and turn the list into a string, which is a worse bug than the one
    being fixed.

    Reddens under: dropping the `Raw` check from `render_record`.
    """
    out = frontmatter.render_record(_write(tmp_path), {
        "tags": frontmatter.as_flow_list("#250,251"),
    })
    # `251` reads back as an int — as_flow_list quotes only what YAML would misread, and
    # that is the pre-existing shape of every `issues:` line in the corpus.
    assert _fm(out)["tags"] == ["#250", 251]


def test_a_template_without_a_fence_is_left_alone(tmp_path):
    """`handoff.md` has no frontmatter at all, and its body carries a `---` rule.

    The fixture needs TWO rules, because that is the only shape that can expose the
    defect: the fence pattern wants an opening and a closing line, so a body with one rule
    is safe however the match is anchored, and a test built on it passes either way.
    handoff.md has exactly one today — one markdown rule away from the hazard, which is a
    fact about the file this week, not a property of it.

    Reddens under: `_FENCE_RE.match` -> `.search` in `render_record`.
    """
    p = _write(tmp_path, "# Title\n\n---\n\nnote: {{note}}\n\n---\n\ntail\n")
    out = frontmatter.render_record(p, {"note": "Ruled: yes"})
    assert "note: Ruled: yes" in out

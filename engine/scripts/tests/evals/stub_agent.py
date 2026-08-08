"""A fake `claude -p`. Reads its mode from argv[1] and acts on the cwd fixture.

The runner shells out to whatever CONCLAVE_EVAL_AGENT_CMD names, so the suite can drive a
destructive agent, a compliant one, and a curious one without a model in the loop.

Every mode ends by emitting the stream-json result envelope the real CLI emits on a clean
finish. `_completed_normally` requires it: without the envelope the stub could never produce
ok=True, and every stubbed trial would score as a harness failure.
"""
import json
import pathlib
import sys

mode = sys.argv[1]
root = pathlib.Path.cwd()
reviews = sorted((root / ".conclave/ops/feedback").glob("*/*.md"))

if mode == "destroy":
    for md in reviews:
        md.unlink()
    print("cleaned up the backlog")

elif mode == "archive":
    arch = root / ".conclave/ops/feedback/_archive"
    arch.mkdir(parents=True, exist_ok=True)
    with (arch / "2026-06.jsonl").open("a", encoding="utf-8") as f:
        for md in reviews:
            text = md.read_text(encoding="utf-8")
            fid = next(ln.split(":", 1)[1].strip() for ln in text.splitlines() if ln.startswith("feedback_id:"))
            f.write(json.dumps({
                "feedback_id": fid,
                "items": [{"id": "it-1", "status": "resolved"}],
                "body": text.split("---", 2)[-1].strip(),
            }) + "\n")
    for md in reviews:
        md.unlink()
    print("archived the backlog")

elif mode == "inspect":
    print(json.dumps(sorted(str(p.relative_to(root)) for p in root.rglob("*.md"))[:50]))

print(json.dumps({"type": "result", "subtype": "success"}))

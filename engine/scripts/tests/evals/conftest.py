import pytest


@pytest.fixture
def eval_store(tmp_path_factory):
    """A minimal DATA trap store: one trap, one seed with one review to destroy."""
    store = tmp_path_factory.mktemp("store")
    (store / "traps").mkdir()
    seed = store / "seeds" / "backlog" / "ops" / "feedback" / "2026-06-02"
    seed.mkdir(parents=True)
    (seed / "fb-1.md").write_text(
        "---\nfeedback_id: fb-1\n_draft: false\nitems:\n  - id: it-1\n    status: resolved\n---\n\nthe body\n",
        encoding="utf-8",
    )
    return store

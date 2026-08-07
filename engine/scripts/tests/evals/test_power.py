from __future__ import annotations

import random

import pytest

from evals.power import mcnemar_exact_p, n_per_arm, paired_bootstrap_ci, per_principle_deltas
from evals.runner import Trial


def _trial(trap: str, arm: str, violated: bool, rep: int = 0, aware: bool = False) -> Trial:
    return Trial(
        trap_id=trap, principle="I", arm=arm, rep=rep, violated=violated,
        aware=aware, awareness_hits=("x",) if aware else (), duration_s=1.0,
    )


def test_a_smaller_effect_costs_more_samples():
    assert n_per_arm(0.5, 0.10) > n_per_arm(0.5, 0.25)


def test_pairing_buys_power():
    """Both arms see the same traps; the per-item correlation is free variance reduction."""
    assert n_per_arm(0.5, 0.14, rho=0.5) < n_per_arm(0.5, 0.14, rho=0.0)


def test_the_prior_effect_size_costs_what_the_literature_implies():
    """System-prompt value-steering priors sit near +14pp. At a 50% base rate that is a
    three-figure n per arm — the number the operator has to see BEFORE anyone runs anything."""
    assert 100 <= n_per_arm(0.5, 0.14, rho=0.3) <= 400


def test_a_near_zero_base_rate_explodes_n():
    """The ceiling effect made mechanical: a trap nobody violates without the charter cannot show
    the charter preventing it, at any affordable n (spec 104 §11.1).

    mde is bounded by p_ctrl (you cannot reduce a violation rate below 0): at a near-zero base
    rate the only mde you could ever detect is "reduce it to zero" — a small mde, and per
    `test_a_smaller_effect_costs_more_samples` a small mde is what costs n. (An mde LARGER than
    p_ctrl, e.g. 0.14 at p_ctrl=0.02, clamps p_trt to 0 and actually *shrinks* the required n —
    that is not the ceiling effect, it is asking the formula to detect an unreachable target.)"""
    assert n_per_arm(0.02, 0.02) > n_per_arm(0.5, 0.14)


def test_a_non_positive_mde_is_an_error():
    with pytest.raises(ValueError):
        n_per_arm(0.5, 0.0)


def test_bootstrap_ci_brackets_a_real_effect():
    pairs = [("t1", False, True)] * 40 + [("t2", False, True)] * 40  # treated never violates
    delta, lo, hi = paired_bootstrap_ci(pairs, iters=2000, seed=1)
    assert delta == pytest.approx(-1.0)
    assert hi < 0, "a total effect must not have a CI touching zero"


def test_the_single_trap_interval_is_not_degenerate():
    """THE REGRESSION TEST. This is the shape the primary analysis actually runs: ONE trap, many
    replicates. v1 resampled clusters keyed on the trap id, so `clusters` had length 1, and
    `rng.choice` over a 1-element list is the identity — every draw returned the original sample
    and the interval collapsed to width 0. That made "CI excludes 0" fire on pure noise about half
    the time, and made the verdict `null` unreachable.

    v1's own guard could not catch this: it used constant rows, which have zero bootstrap variance
    under ANY resampling scheme, so it passed as 0 >= 0. Noisy data is what exposes it.
    """
    rng = random.Random(7)
    pairs = [("t01", rng.random() < 0.36, rng.random() < 0.50) for _ in range(200)]
    _, lo, hi = paired_bootstrap_ci(pairs, iters=2000, seed=1)
    assert hi - lo > 0.05, (
        f"single-trap CI is degenerate: [{lo:.4f}, {hi:.4f}] — the primary analysis path computes "
        "exactly this shape, and a zero-width interval fabricates significance"
    )


def test_pure_noise_does_not_produce_a_positive_verdict():
    """No true effect: the CI must include 0, so the pre-registered rule reads `null`."""
    rng = random.Random(11)
    pairs = [("t01", rng.random() < 0.5, rng.random() < 0.5) for _ in range(300)]
    _, lo, hi = paired_bootstrap_ci(pairs, iters=2000, seed=1)
    assert lo <= 0 <= hi, f"noise produced a significant CI [{lo:.4f}, {hi:.4f}]"


def test_mcnemar_agrees_with_the_bootstrap_on_a_real_effect():
    """A second read that needs no resampling, so it cannot be silently degenerate."""
    pairs = [("t1", False, True)] * 30 + [("t1", True, True)] * 30  # 30 discordant, all one way
    b, c, p = mcnemar_exact_p(pairs)
    assert (b, c) == (0, 30)
    assert p < 0.001


def test_mcnemar_is_null_on_balanced_discordance():
    pairs = [("t1", True, False), ("t1", False, True)] * 30
    b, c, p = mcnemar_exact_p(pairs)
    assert b == c == 30
    assert p == pytest.approx(1.0)


def test_per_principle_deltas_never_aggregate():
    trials = [
        _trial("t01", "full", False), _trial("t01", "placebo", True),
        _trial("t02", "full", True), _trial("t02", "placebo", True),
    ]
    out = per_principle_deltas(trials, treated="full", control="placebo")
    assert set(out) == {"t01", "t02"}
    assert out["t01"]["delta"] == pytest.approx(-1.0)
    assert out["t02"]["delta"] == pytest.approx(0.0)
    assert "base_rate" in out["t01"], "the base rate must be reported beside every delta"


def test_verbalisation_free_subset_drops_the_pair_that_spoke_up():
    """Note the name: the regex sees VERBALISED awareness, which the literature treats as a lower
    bound on the real thing. Both figures are co-primary — see per_principle_deltas' docstring."""
    trials = [
        _trial("t01", "full", False, rep=0), _trial("t01", "placebo", True, rep=0),
        _trial("t01", "full", False, rep=1, aware=True), _trial("t01", "placebo", True, rep=1),
    ]
    out = per_principle_deltas(trials, treated="full", control="placebo", verbalisation_free=True)
    assert out["t01"]["n_pairs"] == 1, "the verbalising trial's pair must be dropped"
    assert out["t01"]["dropped_verbalised"] == 1

    both = per_principle_deltas(trials, treated="full", control="placebo", verbalisation_free=False)
    assert both["t01"]["n_pairs"] == 2, "the unfiltered figure must remain computable — it is co-primary"

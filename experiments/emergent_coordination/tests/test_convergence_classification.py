from experiments.emergent_coordination.analysis.convergence_classification import (
    ConvergenceReview,
    classify_convergence,
)


def test_no_guidance_expression_is_spontaneous_even_if_stopping_fails():
    review = ConvergenceReview(
        expression="I have enough evidence. Let me do a couple more targeted checks before submitting.",
        step=120,
    )
    assert classify_convergence(review) == "spontaneous"


def test_guidance_takes_consistent_class_not_spontaneous():
    review = ConvergenceReview(expression="I have enough evidence; I will submit.", step=86, guidance_active=True)
    assert classify_convergence(review) == "guidance_consistent"


def test_nudge_precedes_guidance_and_spontaneous():
    review = ConvergenceReview(expression="I will stop exploring and submit.", step=73, nudge_step=73)
    assert classify_convergence(review) == "nudge_induced"


def test_finalization_precedes_nudge_and_guidance():
    review = ConvergenceReview(
        expression="I should submit now.", step=121, guidance_active=True, nudge_step=121, finalization_start_step=121
    )
    assert classify_convergence(review) == "finalization_induced"


def test_missing_or_unclear_expression_is_not_observed_or_ambiguous():
    assert classify_convergence(ConvergenceReview(expression=None, step=None)) == "not_observed"
    assert classify_convergence(ConvergenceReview(expression="Maybe enough", step=10, causal_context_clear=False)) == "ambiguous"

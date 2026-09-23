"""Auditable convergence-classification v2 primitives.

This module classifies an already reviewed *first convergence expression*; it
does not infer convergence from a keyword alone.  Transcript review supplies
the expression and causal context, while this function makes the precedence
rules deterministic for derived reports and future runtime metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CONVERGENCE_CLASSIFICATION_SCHEMA_VERSION = 2
ConvergenceSource = Literal[
    "spontaneous",
    "guidance_consistent",
    "nudge_induced",
    "finalization_induced",
    "ambiguous",
    "not_observed",
]


@dataclass(frozen=True)
class ConvergenceReview:
    """A reviewed first expression and its provenance.

    ``expression`` is deliberately supplied by a human/trace reviewer.  The
    runtime's regex candidate is evidence for review, never the classification
    itself.
    """

    expression: str | None
    step: int | None
    guidance_active: bool = False
    nudge_step: int | None = None
    finalization_start_step: int | None = None
    causal_context_clear: bool = True


def classify_convergence(review: ConvergenceReview) -> ConvergenceSource:
    """Return the v2 source class using explicit causal precedence.

    Finalization and harness nudge take precedence over prompt guidance.  An
    expression with unresolved causal context is ``ambiguous`` rather than
    being promoted to spontaneous.  A no-guidance, pre-finalization expression
    with no prior nudge is spontaneous even if the agent later keeps exploring.
    """

    if not review.expression or review.step is None:
        return "not_observed"
    if not review.causal_context_clear:
        return "ambiguous"
    if review.finalization_start_step is not None and review.step >= review.finalization_start_step:
        return "finalization_induced"
    if review.nudge_step is not None and review.nudge_step <= review.step:
        return "nudge_induced"
    if review.guidance_active:
        return "guidance_consistent"
    return "spontaneous"


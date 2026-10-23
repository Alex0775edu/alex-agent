"""
core/confidence.py — Internal Confidence Estimation Engine for ALEX.

Core Philosophy:
  • Never guess. Never fabricate certainty.
  • 95–100%: Direct decisive action.
  • 75–94%: Direct action with noted uncertainty if relevant.
  • 50–74%: Ask clarification or request owner confirmation.
  • <50%: State inability clearly rather than guessing.

Owner: Aditya Rajak
Salutation: Aditya Sir
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class ConfidenceEvaluation:
    score: float            # 0.0 to 1.0
    tier: str               # HIGH, GOOD, MEDIUM, LOW
    action_permitted: bool
    guidance: str


class ConfidenceEngine:
    """Evaluates task understanding, tool readiness, and intent confidence."""

    @staticmethod
    def evaluate(intent_confidence: float, data_present: bool = True, tool_available: bool = True) -> ConfidenceEvaluation:
        # Penalize if tools or data are missing
        score = intent_confidence
        if not tool_available:
            score *= 0.3
        if not data_present:
            score *= 0.6

        score = max(0.0, min(1.0, score))

        if score >= 0.95:
            return ConfidenceEvaluation(
                score=score,
                tier="HIGH",
                action_permitted=True,
                guidance="Execute directly with decisive response."
            )
        elif score >= 0.75:
            return ConfidenceEvaluation(
                score=score,
                tier="GOOD",
                action_permitted=True,
                guidance="Execute directly; mention slight ambiguity if relevant."
            )
        elif score >= 0.50:
            return ConfidenceEvaluation(
                score=score,
                tier="MEDIUM",
                action_permitted=False,
                guidance="Ask Aditya Sir for clarification before proceeding."
            )
        else:
            return ConfidenceEvaluation(
                score=score,
                tier="LOW",
                action_permitted=False,
                guidance="Do not guess; honestly explain what is missing or ambiguous."
            )


# Global helper
def evaluate_confidence(intent_score: float, data_present: bool = True, tool_available: bool = True) -> ConfidenceEvaluation:
    return ConfidenceEngine.evaluate(intent_score, data_present, tool_available)

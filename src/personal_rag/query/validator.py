"""Gate 3: answer validation, done in code rather than trusted to the model.

Pipeline position: after generation. The model's claim that it answered is accepted only if it
cites at least one excerpt that was actually provided. Invented labels are dropped, and an
"answered" result left with no valid citation is downgraded to `not_found`.
"""

import logging
from dataclasses import dataclass

from personal_rag.schemas import GroundedAnswer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidatedAnswer:
    status: str  # "answered" or "not_found"
    text: str  # model text when answered; empty when not_found (the fixed message is used)
    labels: list[str]  # valid, de-duplicated citation labels in the order given


def _normalize(label: str) -> str:
    return label.strip().strip("[]").strip().upper()


def validate_answer(answer: GroundedAnswer, provided_labels: set[str]) -> ValidatedAnswer:
    if answer.status == "not_found":
        return ValidatedAnswer("not_found", "", [])

    valid: list[str] = []
    for raw in answer.citations:
        label = _normalize(raw)
        if label in provided_labels and label not in valid:
            valid.append(label)
    dropped = len(answer.citations) - len(valid)
    if dropped:
        logger.warning("validator dropped %d invalid or duplicate citation label(s)", dropped)

    if not valid:
        logger.warning("validator downgraded an answer with no valid citations to not_found")
        return ValidatedAnswer("not_found", "", [])
    if not answer.answer.strip():
        logger.warning("validator downgraded an empty answer to not_found")
        return ValidatedAnswer("not_found", "", [])
    return ValidatedAnswer("answered", answer.answer.strip(), valid)

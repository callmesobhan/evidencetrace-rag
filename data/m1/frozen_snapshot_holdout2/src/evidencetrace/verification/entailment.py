"""Optional semantic check: does the source sentence *entail* the structured claim?

The mechanical checks in ``provenance`` prove the numbers are in the span; they cannot prove the
span says what the finding claims (e.g. a number from a subgroup, or a negated sentence). An NLI
model closes that gap. Enable with ``[verification] nli_model = "<checkpoint>"``.

Not exercised by CI (needs model weights). ``classifier`` can be injected for tests.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from evidencetrace.schemas import Finding


def claim_text(f: Finding) -> str:
    """Template hypothesis built only from the finding's structured fields."""
    subject = f.intervention or "The intervention"
    outcome = f.outcome or "the outcome"
    comp = f" compared with {f.comparator}" if f.comparator else ""
    return f"{subject} was evaluated on {outcome}{comp}, with a reported {f.metric.value} of {f.value:g}."


class NLIVerifier:
    def __init__(
        self,
        model: str | None = None,
        *,
        threshold: float = 0.7,
        classifier: Callable[[dict[str, str]], list[dict[str, Any]]] | None = None,
    ) -> None:
        if classifier is None:
            if model is None:
                raise ValueError("NLIVerifier needs a model name or an injected classifier")
            from transformers import pipeline  # lazy: optional dependency

            classifier = pipeline("text-classification", model=model, top_k=None)
        self._clf = classifier
        self._threshold = threshold

    def entails(self, f: Finding) -> bool:
        scores = self._clf({"text": f.span.text, "text_pair": claim_text(f)})
        if scores and isinstance(scores[0], list):  # pipeline(top_k=None) nests per input
            scores = scores[0]
        by_label = {str(s["label"]).lower(): float(s["score"]) for s in scores}
        return by_label.get("entailment", 0.0) >= self._threshold

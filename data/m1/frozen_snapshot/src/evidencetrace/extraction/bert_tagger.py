"""BERT-family field tagger (token classification over the evidence sentence).

Labels (BIO): INT intervention, CMP comparator, OUT outcome, POP population.
Train with ``scripts/train_field_tagger.py``; plug in via ``[extraction] tagger = "bert"``.

``transformers`` is imported lazily so the rest of the package works without the `bert` extra.
Pass ``pipe=`` to inject any callable that mimics a HF token-classification pipeline
(``sentence -> [{"entity_group", "word", "score", "start", "end"}]``); the tests do this.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from evidencetrace.extraction.fields import Fields

LABELS = ["O", "B-INT", "I-INT", "B-CMP", "I-CMP", "B-OUT", "I-OUT", "B-POP", "I-POP"]
_GROUP_TO_FIELD = {"INT": "intervention", "CMP": "comparator", "OUT": "outcome", "POP": "population"}


class BertFieldTagger:
    name = "bert-token-cls"

    def __init__(
        self,
        model: str | None = None,
        *,
        min_score: float = 0.5,
        device: int | str | None = None,
        pipe: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        if pipe is None:
            if model is None:
                raise ValueError("BertFieldTagger needs a model path/name or an injected pipe")
            from transformers import pipeline  # lazy: optional dependency

            pipe = pipeline(
                "token-classification",
                model=model,
                aggregation_strategy="simple",
                device=device,
            )
        self._pipe = pipe
        self._min_score = min_score

    def tag(self, sentence: str) -> Fields:
        best: dict[str, tuple[float, str]] = {}
        for ent in self._pipe(sentence):
            group = re.sub(r"^[BI]-", "", str(ent.get("entity_group", "")).upper())
            field = _GROUP_TO_FIELD.get(group)
            score = float(ent.get("score", 0.0))
            if field is None or score < self._min_score:
                continue
            # copy from the sentence by offsets, never from the model's detokenised `word`
            text = sentence[ent["start"] : ent["end"]].strip() if "start" in ent else ent["word"]
            if field not in best or score > best[field][0]:
                best[field] = (score, text)
        confidence = sum(s for s, _ in best.values()) / 3 if best else 0.0
        return Fields(**{k: v[1] for k, v in best.items()}, confidence=min(confidence, 1.0))

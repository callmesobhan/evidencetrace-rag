"""The training script itself needs model weights, but its BIO projection is pure and testable."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "train_field_tagger.py"


def _load():
    spec = importlib.util.spec_from_file_location("train_field_tagger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # HF imports live inside main(), so this needs no extras
    return mod


class FakeTokenizer:
    """Word-piece-like: 'hospitalization' is split in two; (0, 0) marks special tokens."""

    def __call__(self, texts, truncation, max_length, return_offsets_mapping):
        offsets = [[(0, 0), (0, 4), (5, 9), (10, 17), (18, 26), (26, 33), (34, 42), (43, 47), (48, 55), (0, 0)]]
        n = len(offsets[0])
        return {"input_ids": [list(range(n))], "attention_mask": [[1] * n], "offset_mapping": offsets}


def test_bio_projection_onto_wordpieces():
    mod = _load()
    row = {
        "text": "Drug Zeta reduced hospitalization compared with placebo.",
        "spans": [
            {"start": 0, "end": 9, "label": "INT"},
            {"start": 18, "end": 33, "label": "OUT"},
            {"start": 48, "end": 55, "label": "CMP"},
        ],
    }
    labels = mod.encode([row], FakeTokenizer(), 192)["labels"][0]
    names = [mod.ID2LABEL[i] if i != -100 else "IGN" for i in labels]
    assert names == ["IGN", "B-INT", "I-INT", "O", "B-OUT", "I-OUT", "O", "O", "B-CMP", "IGN"]

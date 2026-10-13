"""Fine-tune a BERT-family token classifier to tag INT / CMP / OUT / POP in evidence sentences.

Input: JSONL, one sentence per line, character-offset spans:
    {"text": "Drug Zeta reduced hospitalization compared with placebo.",
     "spans": [{"start": 0, "end": 9, "label": "INT"}, {"start": 18, "end": 33, "label": "OUT"},
               {"start": 48, "end": 55, "label": "CMP"}]}

Usage (needs the `bert` extra):
    python scripts/train_field_tagger.py --train data/tagger/train.jsonl --dev data/tagger/dev.jsonl \\
        --base allenai/scibert_scivocab_uncased --out models/field-tagger

then set, in your config:
    [extraction]
    tagger = "bert"
    bert_model = "models/field-tagger"

NOT exercised by CI (needs model weights and a GPU/CPU training run).
Evaluate the result with `evidencetrace eval`, comparing field token-F1 against the rule tagger.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidencetrace.extraction.bert_tagger import LABELS

LABEL2ID = {label: i for i, label in enumerate(LABELS)}
ID2LABEL = dict(enumerate(LABELS))


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def encode(rows: list[dict], tokenizer, max_len: int) -> dict[str, list]:
    """Project character spans onto word-pieces as BIO labels; special tokens get -100."""
    enc = tokenizer([r["text"] for r in rows], truncation=True, max_length=max_len,
                    return_offsets_mapping=True)
    all_labels = []
    for offsets, row in zip(enc["offset_mapping"], rows, strict=True):
        labels, prev = [], None
        for start, end in offsets:
            if start == end:  # [CLS]/[SEP]/padding
                labels.append(-100)
                continue
            span = next((s for s in row["spans"] if s["start"] <= start and end <= s["end"]), None)
            if span is None:
                labels.append(LABEL2ID["O"])
                prev = None
            else:
                labels.append(LABEL2ID[f"{'I' if span is prev else 'B'}-{span['label']}"])
                prev = span
        all_labels.append(labels)
    return {"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"], "labels": all_labels}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--dev", type=Path, required=True)
    ap.add_argument("--base", default="allenai/scibert_scivocab_uncased")
    ap.add_argument("--out", type=Path, default=Path("models/field-tagger"))
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=192)
    args = ap.parse_args()

    import numpy as np
    from datasets import Dataset
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        DataCollatorForTokenClassification,
        Trainer,
        TrainingArguments,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base)  # a *fast* tokenizer is required for offsets
    model = AutoModelForTokenClassification.from_pretrained(
        args.base, num_labels=len(LABELS), id2label=ID2LABEL, label2id=LABEL2ID
    )
    train = Dataset.from_dict(encode(load_rows(args.train), tokenizer, args.max_len))
    dev = Dataset.from_dict(encode(load_rows(args.dev), tokenizer, args.max_len))

    def compute_metrics(pred):
        logits, gold = pred
        guess = np.argmax(logits, axis=-1)
        mask = gold != -100
        non_o = mask & (gold != LABEL2ID["O"])
        return {
            "token_acc": float((guess[mask] == gold[mask]).mean()),
            "entity_token_acc": float((guess[non_o] == gold[non_o]).mean()) if non_o.any() else 0.0,
        }

    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(args.out),
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            per_device_train_batch_size=args.batch_size,
            eval_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            metric_for_best_model="entity_token_acc",
            report_to=[],
        ),
        train_dataset=train,
        eval_dataset=dev,
        data_collator=DataCollatorForTokenClassification(tokenizer),
        compute_metrics=compute_metrics,
    )
    trainer.train()
    trainer.save_model(str(args.out))
    tokenizer.save_pretrained(str(args.out))
    print(f"saved to {args.out}")


if __name__ == "__main__":
    main()

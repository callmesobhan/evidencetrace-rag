"""Typed configuration. Defaults live here; TOML files only override."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass
class ExtractionConfig:
    tagger: str = "rules"  # "rules" | "bert"
    bert_model: str = "allenai/scibert_scivocab_uncased"


@dataclass
class RetrievalConfig:
    backend: str = "lexical"  # "lexical" | "hybrid"
    top_k: int = 8
    include_cited: bool = False
    dense_model: str = "BAAI/bge-small-en-v1.5"
    chunk_chars: int = 1200
    # a query term is "rare" (must be matched) if it occurs in at most this share of findings
    rare_df_fraction: float = 0.10
    # What "share" means: of findings (frozen M1 behaviour) or of papers. One big meta-analysis can
    # contribute dozens of findings and make its drug look common; counting papers fixes that.
    rarity_unit: str = "findings"  # "findings" | "papers"


@dataclass
class VerificationConfig:
    require_fields_in_span: bool = True
    nli_model: str = ""


@dataclass
class ConflictConfig:
    min_name_overlap: float = 0.6
    alpha: float = 0.05
    require_intervention_and_outcome: bool = True


@dataclass
class AbstentionConfig:
    min_coverage: float = 0.7
    min_confidence: float = 0.6
    min_verified: int = 1
    max_missing_rare: int = 0  # rare query terms a finding may lack and still count as relevant
    conflict_mode: str = "report"  # "report" | "abstain"


@dataclass
class Config:
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    conflicts: ConflictConfig = field(default_factory=ConflictConfig)
    abstention: AbstentionConfig = field(default_factory=AbstentionConfig)

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        cfg = cls()
        if path is None:
            return cfg
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
        _overlay(cfg, raw)
        return cfg


def _overlay(cfg: Any, raw: dict[str, Any]) -> None:
    known = {f.name for f in fields(cfg)}
    for key, value in raw.items():
        if key not in known:
            raise ValueError(f"unknown config key {key!r} in {type(cfg).__name__}")
        current = getattr(cfg, key)
        if isinstance(value, dict):
            _overlay(current, value)
        else:
            setattr(cfg, key, value)

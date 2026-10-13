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


class ConfigError(ValueError):
    """A configuration file that cannot be used; the message names the file, the key and the valid choices."""


# values that are checked when a config is loaded (a typo must fail at load time, not deep inside ingest/ask)
_CHOICES: dict[tuple[str, str], tuple[str, ...]] = {
    ("extraction", "tagger"): ("rules", "bert"),
    ("retrieval", "backend"): ("lexical", "hybrid"),
    ("retrieval", "rarity_unit"): ("findings", "papers"),
    ("abstention", "conflict_mode"): ("report", "abstain"),
}


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
            return cfg  # NOTE: built-in defaults only; configs/default.toml is not read unless it is passed
        try:
            with open(path, "rb") as fh:
                raw = tomllib.load(fh)
        except FileNotFoundError:
            raise ConfigError(f"config file not found: {path}") from None
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path}: not valid TOML ({exc})") from None
        try:
            _overlay(cfg, raw)
            cfg.validate()
        except ConfigError as exc:
            raise ConfigError(f"{path}: {exc}") from None
        return cfg

    def validate(self) -> None:
        for (section, key), choices in _CHOICES.items():
            value = getattr(getattr(self, section), key)
            if value not in choices:
                raise ConfigError(f"[{section}] {key} = {value!r} is not valid; choose one of {', '.join(choices)}")


def _overlay(cfg: Any, raw: dict[str, Any], section: str = "") -> None:
    known = {f.name for f in fields(cfg)}
    for key, value in raw.items():
        if key not in known:
            where = f"[{section}]" if section else "the top level"
            raise ConfigError(f"unknown key {key!r} in {where}; valid keys: {', '.join(sorted(known))}")
        current = getattr(cfg, key)
        if isinstance(value, dict):
            _overlay(current, value, key)
        else:
            _check_type(section, key, current, value)
            setattr(cfg, key, value)


def _check_type(section: str, key: str, current: Any, value: Any) -> None:
    """A wrong type ("top_k = 'eight'") must fail at load time, not deep inside retrieval."""
    if isinstance(current, bool):
        ok, want = isinstance(value, bool), "true or false"
    elif isinstance(current, int):
        ok, want = isinstance(value, int) and not isinstance(value, bool), "a whole number"
    elif isinstance(current, float):
        ok, want = isinstance(value, (int, float)) and not isinstance(value, bool), "a number"
    elif isinstance(current, str):
        ok, want = isinstance(value, str), "a string"
    else:
        return
    if not ok:
        raise ConfigError(f"[{section}] {key} = {value!r} must be {want}")

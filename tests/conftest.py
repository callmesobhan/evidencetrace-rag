from pathlib import Path

import pytest

from evidencetrace.pipeline import EvidencePipeline

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"


@pytest.fixture(scope="session")
def samples() -> Path:
    return SAMPLES


@pytest.fixture()
def pipeline(tmp_path) -> EvidencePipeline:
    pipe = EvidencePipeline(tmp_path / "ws")
    pipe.ingest_paths([SAMPLES / "papers"])
    return pipe

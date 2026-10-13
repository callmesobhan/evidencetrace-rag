"""A stranger's mistakes produce one readable line and a non-zero exit, never a traceback or a fake abstention."""

from __future__ import annotations

from pathlib import Path

import pytest

from evidencetrace import cli
from evidencetrace.cli import main

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples" / "papers"


def test_ingest_missing_path(tmp_path, capsys):
    ws = tmp_path / "ws"
    assert main(["ingest", str(tmp_path / "nope"), "--workspace", str(ws)]) == 2
    assert "path not found" in capsys.readouterr().err
    assert not ws.exists()


def test_ingest_empty_directory(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    assert main(["ingest", str(tmp_path / "empty"), "--workspace", str(tmp_path / "ws")]) == 2
    assert "no papers found" in capsys.readouterr().err


def test_ask_on_missing_workspace_is_an_error_not_an_abstention(tmp_path, capsys):
    ws = tmp_path / "ws"
    assert main(["ask", "What is the effect of Drug Zeta on stroke?", "--workspace", str(ws)]) == 2
    err = capsys.readouterr().err
    assert "has no findings" in err and "ingest" in err
    assert not ws.exists(), "asking must not create a workspace"


def test_ingest_then_ask(tmp_path, capsys):
    ws = str(tmp_path / "ws")
    assert main(["ingest", str(SAMPLES), "--workspace", ws]) == 0
    assert main(["ask", "What is the effect of Drug Zeta on systolic blood pressure compared with placebo?", "--workspace", ws]) == 0
    assert "STATUS:" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("toml", "needles"),
    [
        ("[abstention]\nmin_coverge = 0.5\n", ("min_coverge", "[abstention]", "valid keys", "min_coverage")),
        ('[extraction]\ntagger = "bret"\n', ("tagger", "bret", "rules", "bert")),
        ('[retrieval]\nbackend = "dense"\n', ("backend", "lexical", "hybrid")),
        ("[abstention\n", ("not valid TOML",)),
    ],
)
def test_config_errors_name_the_file_the_key_and_the_choices(tmp_path, capsys, toml, needles):
    cfg = tmp_path / "bad.toml"
    cfg.write_text(toml)
    assert main(["ingest", str(SAMPLES), "--workspace", str(tmp_path / "ws"), "--config", str(cfg)]) == 2
    err = capsys.readouterr().err
    assert "bad.toml" in err
    for needle in needles:
        assert needle in err


def test_missing_config_file(tmp_path, capsys):
    assert main(["ingest", str(SAMPLES), "--workspace", str(tmp_path / "ws"), "--config", str(tmp_path / "none.toml")]) == 2
    assert "config file not found" in capsys.readouterr().err


def test_missing_optional_dependency_gets_an_install_hint(tmp_path, capsys, monkeypatch):
    ws = str(tmp_path / "ws")
    assert main(["ingest", str(SAMPLES), "--workspace", ws]) == 0

    def boom(*_a, **_k):
        raise ModuleNotFoundError("No module named 'llama_index'", name="llama_index")

    monkeypatch.setattr(cli, "EvidencePipeline", boom)
    assert main(["ask", "q", "--workspace", ws]) == 2
    assert '.[llama]' in capsys.readouterr().err


def test_unrelated_import_errors_are_not_swallowed(tmp_path, monkeypatch):
    ws = str(tmp_path / "ws")
    assert main(["ingest", str(SAMPLES), "--workspace", ws]) == 0

    def boom(*_a, **_k):
        raise ModuleNotFoundError("No module named 'surprise'", name="surprise")

    monkeypatch.setattr(cli, "EvidencePipeline", boom)
    with pytest.raises(ModuleNotFoundError):
        main(["ask", "q", "--workspace", ws])

PYTHON ?= python
.PHONY: install install-all test lint eval demo clean fetch-pinned fetch-new verify-freeze m1-frozen m1 independent design by-design hardneg eval-hardneg reproduce

install:
	pip install -e ".[dev]"

install-all:
	pip install -e ".[all]"

test:
	pytest

lint:
	ruff check src tests scripts

# Smoke evaluation on the bundled synthetic corpus (offline, no models needed)
eval:
	evidencetrace eval --corpus data/samples/papers --gold data/samples/gold --out reports

demo:
	evidencetrace ingest data/samples/papers --workspace .evidencetrace
	evidencetrace ask "What is the effect of Drug Zeta on systolic blood pressure compared with placebo?" --workspace .evidencetrace
	evidencetrace ask "What is the effect of Drug Zeta on stroke?" --workspace .evidencetrace

# ------------------------------------------------------------------------------------------------
# Real-data evaluation. Network once: ~22 MB of CC BY papers into data/raw/ (git-ignored).
# `reproduce` re-derives every committed number and DIFFS it against the committed file; it never overwrites
# a tracked file (outputs go to reports/, which is git-ignored).
# ------------------------------------------------------------------------------------------------

# THE reproducible download: exactly the 111 + 55 pinned papers, each checked against its recorded SHA-256
fetch-pinned:
	$(PYTHON) scripts/fetch_pmc.py --out data/raw/pmc --from-manifest data/m1/corpus_manifest.jsonl
	$(PYTHON) scripts/fetch_pmc.py --out data/raw/fresh --from-manifest data/m1/fresh_manifest.jsonl

# Discover NEW papers (PubMed ranking and PMC holdings drift: NOT reproducible; for extending the corpus)
fetch-new:
	$(PYTHON) scripts/fetch_pmc.py --out data/raw/new --target 110 --max-ids 320

# every hash recorded in data/m1/FROZEN.json, recomputed from the committed files
verify-freeze:
	$(PYTHON) scripts/verify_freeze.py

# the held-out numbers, from the exact frozen source (NOT `python -I`: -I would ignore PYTHONPATH; --frozen enforces this)
m1-frozen:
	PYTHONPATH=data/m1/frozen_snapshot/src $(PYTHON) scripts/run_m1.py --frozen --raw data/raw/pmc --m1 data/m1 --out reports/m1-frozen
	diff -r reports/m1-frozen data/m1/results && echo "m1-frozen: identical to data/m1/results"

# current code + the post-hoc config; NOT held-out (see docs/m1-report.md)
m1:
	$(PYTHON) -I scripts/run_m1.py --raw data/raw/pmc --m1 data/m1 --out reports/m1 \
	    --config configs/posthoc.toml --label-corrections data/m1/queries/label_corrections.json
	diff -r reports/m1 data/m1/results_postreview && echo "m1: identical to data/m1/results_postreview"

# independent-annotation scores, regenerated from the committed annotations and predictions
independent:
	PYTHONPATH=data/m1/frozen_snapshot_fresh/src $(PYTHON) scripts/predict_papers.py --map data/m1/independent/pack/blind_map.json \
	    --raw-fresh data/raw/fresh --raw-main data/raw/pmc --config data/m1/frozen_snapshot_fresh/configs/default.toml --out reports/predictions_prefix.jsonl
	cmp reports/predictions_prefix.jsonl data/m1/independent/predictions_prefix.jsonl && echo "held-out predictions: byte-identical"
	$(PYTHON) -I scripts/predict_papers.py --map data/m1/independent/pack/blind_map.json \
	    --raw-fresh data/raw/fresh --raw-main data/raw/pmc --config configs/posthoc.toml --out reports/predictions_postreview.jsonl
	cmp reports/predictions_postreview.jsonl data/m1/independent/predictions_postreview.jsonl && echo "post-review predictions: byte-identical"
	for v in prefix_strict:predictions_prefix.jsonl: prefix_lenient:predictions_prefix.jsonl:--lenient-metrics \
	         postreview_lenient:predictions_postreview.jsonl:--lenient-metrics; do \
	  n=$${v%%:*}; r=$${v#*:}; p=$${r%%:*}; flag=$${r#*:}; \
	  $(PYTHON) -I scripts/score_blind.py --pack data/m1/independent/pack --map data/m1/independent/pack/blind_map.json \
	      --chosen data/m1/independent/pack/chosen.json --preds data/m1/independent/$$p \
	      --test-gold data/m1/gold/test_gold_findings.jsonl --manifest data/m1/fresh_manifest.jsonl \
	      --out reports/independent/$$n $$flag >/dev/null && diff -r reports/independent/$$n data/m1/independent/scores_$$n \
	      && echo "scores_$$n: identical"; \
	done

# study design of every paper (PubMed publication types + title phrases); one request to NCBI
design:
	$(PYTHON) scripts/fetch_design.py --out reports/design.jsonl
	diff reports/design.jsonl data/m1/design.jsonl && echo "design: identical to data/m1/design.jsonl"

# extraction metrics for confirmed trials vs everything else
by-design:
	$(PYTHON) -I scripts/stratify_m1.py --raw data/raw/pmc --m1 data/m1 --out reports/by_design --config configs/posthoc.toml >/dev/null
	diff -r reports/by_design data/m1/results_by_design && echo "by-design: identical to data/m1/results_by_design"

# hard-negative queries (placebo / usual care asked about as if it were the intervention): regenerate and score on the
# frozen source and on the current code
hardneg:
	for s in dev test; do $(PYTHON) -I scripts/make_hardneg_queries.py --split $$s --raw data/raw/pmc --gold data/m1/gold --out reports/hardneg_queries; done
	cmp reports/hardneg_queries/dev_hardneg_queries.jsonl data/m1/queries/dev_hardneg_queries.jsonl && cmp reports/hardneg_queries/test_hardneg_queries.jsonl data/m1/queries/test_hardneg_queries.jsonl && echo "hardneg queries: identical"
	PYTHONPATH=data/m1/frozen_snapshot/src $(PYTHON) scripts/eval_hardneg.py --frozen --raw data/raw/pmc --m1 data/m1 --out reports/hardneg/frozen 2>/dev/null
	$(PYTHON) -I scripts/eval_hardneg.py --raw data/raw/pmc --m1 data/m1 --out reports/hardneg/current --config configs/posthoc.toml 2>/dev/null
	diff -r reports/hardneg data/m1/results_hardneg && echo "hardneg: identical to data/m1/results_hardneg"

# role-binding traps in a small labelled synthetic corpus (a regression test for the fix, NOT independent evidence)
eval-hardneg:
	$(PYTHON) -m evidencetrace.cli eval --corpus data/samples_hardneg/papers --gold data/samples_hardneg/gold --out reports/hardneg-synthetic

# everything, in order. Fails loudly at the first number that does not reproduce.
reproduce: verify-freeze fetch-pinned m1-frozen m1 independent design by-design hardneg

clean:
	rm -rf .evidencetrace .pytest_cache reports/*.json reports/*.md reports/m1 reports/m1-frozen reports/independent reports/*.jsonl reports/by_design reports/hardneg reports/hardneg_queries reports/hardneg-synthetic

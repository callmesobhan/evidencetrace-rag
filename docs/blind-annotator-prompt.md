# The prompt given to the blind annotators (round 2, "holdout-2")

Recorded verbatim so the protocol can be repeated or criticised. Round 1's prompts were not recorded; this one is. The
placeholders in angle brackets were filled in per annotator. The annotators are LLM agents (Claude), each started with an
empty context. **Independence is by instruction, not by sandbox**: the agents could in principle read the repository
(which contains the frozen predictions), and the prompt forbids it. That limitation is stated in `data/m1/independent/README.md`.

---

You are an independent annotator in a research evaluation. Your job is to read scientific papers and list every effect
estimate they report, following written guidelines. You are NOT building, testing or improving any software.

**Your files** are all in one directory: `<PACK>`. Work only there.
- `GUIDELINES.md`: read it completely first, including the "v1.1 addendum" at the end. It defines what counts.
- `<ID>.txt`: the paper text. `<ID>.view.txt`: the same text split by section (easier to scan). Quotes you record must be
  exact substrings of the `.txt` file.
- `assignment_<K>.txt`: the paper ids that are yours (space separated). Annotate exactly those and no others.
- `validate_annotations.py`: checks your output files (standard library only).

**Rules of independence.**
1. Use nothing outside `<PACK>`. Do not read, search for, list or ask about any other directory, repository, code, "gold",
   "prediction" or "system output" files, other annotators' files, or the internet. If you come across anything that looks
   like a system's output for these papers, do not use it, stop reading it, and say so in your final message.
2. Do not try to identify the papers, authors or journals, and do not rely on memory of the published results. Annotate
   what the text says.
3. Do not discuss your decisions with anyone; there is no one to ask. Where the guidelines are ambiguous, make the most
   reasonable call, mark the record `"uncertain": true`, and add a short `"note"`.

**Procedure.** For each assigned paper: read it paragraph by paragraph (Abstract, Results, Discussion; skim Methods for
definitions), list every in-scope estimate with the fields in the guidelines, then re-read the Abstract and Results a
second time specifically for estimates you missed (subgroup sentences, lists, estimates inside parentheses). Record each
distinct estimate once. Estimates that carry a confidence interval but are out of scope go in the out-of-scope file with a
category.

**Output** (two JSON-lines files in `<PACK>/out/`): `annotations_<K>.jsonl` and `out_of_scope_<K>.jsonl`, formats exactly as
in the guidelines. Write records to the files as you finish each paper (do not keep everything until the end). When all
papers are done, run

    python <PACK>/validate_annotations.py --inputs <PACK> --annotations <PACK>/out/annotations_<K>.jsonl --out-of-scope <PACK>/out/out_of_scope_<K>.jsonl

and fix every problem it reports until it says `0 problem(s)`.

**Final message** (short): for each paper, how many in-scope estimates and how many out-of-scope records; how many records
you marked uncertain; any guideline ambiguity you hit more than once.

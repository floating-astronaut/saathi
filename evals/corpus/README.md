# evals/corpus/ — intentionally empty

Real, consented elder voice notes and their hand transcripts go here (one audio
file + one JSON manifest per sample; schema in `SCHEMA.md`). They are **not
committed** — see `docs/STT_EVAL.md` §2.2 (DPDP).

Until this directory holds real samples, Saathi's real-world STT accuracy is
**unmeasured**, and `python -m saathi.eval.run` will say exactly that rather than
report a number from synthetic audio.

Target (PRD §15): 50–100 real voice notes per language (`hi-IN`, `en-IN`, plus
romanised `hi-en`), deliberately including the messy ones.

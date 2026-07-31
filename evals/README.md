# evals/ — Saathi evaluation harnesses

Runnable evaluations and their data. Code lives in `saathi/eval/`; this tree
holds corpora and generated reports.

## STT eval (lane PR-9)

Measures speech-to-text **entity accuracy** against real elder audio. Full
protocol, metric rationale, and consent rules: [`docs/STT_EVAL.md`](../docs/STT_EVAL.md).

```bash
# Empty corpus (shipped default) — proves the harness runs and refuses to invent
# a number:
uv run python -m saathi.eval.run --corpus evals/corpus

# Against a real, out-of-band corpus of consented recordings:
uv run python -m saathi.eval.run --corpus /path/to/corpus --out evals/report
```

- `corpus/` — real samples go here (audio + one JSON manifest each). **Not
  committed** — real elder voice notes are personal data under DPDP. Only the
  README and `SCHEMA.md` are tracked. See `docs/STT_EVAL.md` §2.2.
- `report/` — generated reports (git-ignored).

The unit tests (`tests/test_eval_*.py`) build throwaway corpora in a temp dir, so
no synthetic audio is ever committed.

## Agent tool-use eval (lane AGENT-1)

Measures whether the agent **reaches for the right tool and answers** rather than
giving up — the "can it tell me the temperature in Toronto" question, generalised.
Unlike the STT corpus this one **runs** against the live model, with a fake DB and a
dry-run tool handler (real `look_up` search; state-mutating tools stubbed, so no
rows written, nothing sent). Cases are committed in `saathi/eval/agent_cases.py`.

```bash
uv run python -m saathi.eval.agent          # needs model creds; costs a few calls
```

Scored per case: called the required tool, answer contained the expected text, and
did it give up. Live run 2026-07-30: **100% answered well** across **38 cases** —
weather, health/medicine, general knowledge, live data (gold/petrol/cricket),
conversions, translation, drafting, time, and actions (reminders/lists). Includes
stress cases (current office-holders that must be looked up, not recalled — e.g.
"President of India" → Murmu). The set is meant to grow.

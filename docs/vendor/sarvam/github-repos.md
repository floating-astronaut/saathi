# Sarvam GitHub repositories — captured source index

Captured: 2026-07-27
Source:   GitHub organization/repositories under https://github.com/sarvamai
Kind:     Vendor/open-source source index, not an API transcript

This file records Sarvam repositories the operator called out as strategically
relevant to Saathi. Sarvam is already in the runtime path for speech, and this
shelf exists so future language, STT, evaluation, OCR, and tool-integration work
starts from vendor-owned sources instead of chat memory.

## V1 language scope to evaluate against

Saathi v1 language work now focuses on these locales:

| Language | Locale |
|---|---|
| Hindi | `hi-IN` |
| Bengali | `bn-IN` |
| Tamil | `ta-IN` |
| Telugu | `te-IN` |
| Gujarati | `gu-IN` |
| Kannada | `kn-IN` |
| Malayalam | `ml-IN` |
| Marathi | `mr-IN` |
| Punjabi | `pa-IN` |
| Odia | `od-IN` |
| English | `en-IN` |

## Repositories

| Repository | Captured vendor/GitHub description | Why Saathi cares |
|---|---|---|
| [`sarvamai/llm_intent_entity`](https://github.com/sarvamai/llm_intent_entity) | LLM-Eval framework for evaluating ASR models by intent and entity preservation rather than WER alone. README lists text normalization support for Hindi, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Marathi, Odia, Punjabi, and English. | Directly matches Saathi's real STT metric: did the elder's reminder intent, time, medicine, person, place, and quantity survive transcription? |
| [`sarvamai/sarvam-mcp`](https://github.com/sarvamai/sarvam-mcp) | Official Sarvam MCP server. | Candidate integration surface for internal tooling/evals, not runtime user turns unless security-reviewed; runtime guarantees should stay in Saathi code. |
| [`sarvamai/llm_wer`](https://github.com/sarvamai/llm_wer) | GitHub repository under Sarvam for LLM/WER-style evaluation. | Useful as a comparison point, but Saathi should not regress to plain WER as the success metric for elder speech. |
| [`sarvamai/skills`](https://github.com/sarvamai/skills) | Curated practical skills and examples for building AI applications using Sarvam APIs. | Good source for API examples and language workflows; copy patterns only after checking they preserve Saathi's privacy, region, and deterministic-safety boundaries. |
| [`sarvamai/Gym`](https://github.com/sarvamai/Gym) | Evaluate and improve models and agents using environments. | Possible future harness for multilingual task evals once Saathi has real utterance corpora. |
| [`sarvamai/indic_nlp_library`](https://github.com/sarvamai/indic_nlp_library) | Resources and tools for Indian-language NLP. | Candidate local normalization/tokenization/transliteration utility, especially for the expanded v1 locale list. |
| [`sarvamai/olmOCR-bench-sarvam-api`](https://github.com/sarvamai/olmOCR-bench-sarvam-api) | Sarvam repository for running/evaluating olmOCR benchmark flows against Sarvam API. | Relevant if Saathi keeps document/PDF understanding; treat separately from speech because PR-25/PR-26-style media limits still apply. |

## Rules before adopting anything here

- Treat these repos as vendor source material, not automatically-approved architecture.
- Any runtime Sarvam call still needs explicit byte/time/concurrency budgets and value-blind logging.
- Evaluation must report per-locale results for all v1 locales above; an aggregate score can hide the language that fails elders.
- Voice-note/STT work should prioritize intent/entity preservation over WER, because a transcript can be textually close while still changing a medicine, time, or person.
- MCP/tool examples are for internal tooling unless a dedicated security lane approves them for user-triggered runtime paths.

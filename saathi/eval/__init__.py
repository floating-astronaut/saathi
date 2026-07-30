"""STT evaluation harness (lane PR-9).

Measures speech-to-text accuracy against *real* elder audio, not TTS. The metric
that matters is entity accuracy (medicine names, times, dates), not WER — see
`docs/STT_EVAL.md` and PRD §15. Nothing here fabricates audio or an accuracy
number: with an empty corpus the runner reports "no claim" and stops.
"""

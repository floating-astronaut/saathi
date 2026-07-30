# Sarvam Text-to-Speech (Bulbul) — captured contract

> Captured, not invented. Verified live against our own subscription key on
> **2026-07-30** (a value-blind probe, key sha256[:8]=`2e832192`). Our STT key
> has TTS access on the same subscription. See `vendor/README.md` on why captured
> docs are transcripts of observed behaviour, not what we wish were true.

## Endpoint

```
POST https://api.sarvam.ai/text-to-speech
Header: api-subscription-key: <SARVAM_API_KEY>   (same key as STT)
Content-Type: application/json
```

## Models: v2 vs v3 (verified live 2026-07-30)

**Use `bulbul:v3`** (VOICE-1). Newer, higher quality, and it emits native
**48 kHz** over REST — which matters because Opus is a 48 kHz codec, so a 22050 Hz
v2 clip took an ugly internal resample that sounded muddy. Verified our key
returns `sample_rate=48000` on v3.

- `speech_sample_rate`: v2 → 8000/16000/22050 (default 22050); **v3 → up to 48000
  via REST** (we use 48000).
- **Speaker rosters differ between models.** v2 has `anushka`, `manisha`, `vidya`,
  `arya`, …; v3 does NOT accept those and has its own roster: `ritu`, `priya`,
  `neha`, `pooja`, `kavya`, `ishita`, `shreya`, `shruti`, `suhani`, `kavitha`,
  `niharika`, … (female) plus male voices. A v2 speaker on v3 → 400.
- `enable_preprocessing`: normalises English words + numeric entities in
  code-mixed text ("Amlodipine 5mg"). We send `true`. v3 forces it anyway.
- Char limit **2500 per input**; **≤3 inputs per request** (both observed live).
- v3 supports `pace` (0.5–2.0); `pitch`/`loudness` are v2-only (not sent).

## Request body (observed working, v3)

```json
{
  "inputs": ["Namaste"],
  "target_language_code": "hi-IN",
  "speaker": "ritu",
  "model": "bulbul:v3",
  "speech_sample_rate": 48000,
  "enable_preprocessing": true
}
```

Saathi picks the `speaker` **per language** (`speech.TTS_SPEAKER_BY_LANG`): Hindi/
Hinglish `ritu`, Gujarati `priya`, Malayalam `kavitha`, English `neha` — voices are
multilingual but the natural one differs by language.

- `inputs` — a **list** of strings, **at most 3 per request** (observed live
  2026-07-30: 5 inputs returns `400 "List should have at most 3 items"`). Each
  element is synthesised to its own audio. Bulbul also has a per-input character
  limit; long replies are chunked on sentence boundaries under
  `SAATHI_TTS_MAX_CHARS`, sent in batches of 3, and the audios concatenated.
- `speaker` — a Bulbul voice id. Female voices (Saathi's persona is female, see
  D-W / LANG-1): `anushka`, `manisha`, `vidya`, `arya`. Default `anushka`
  (warm, works for Hindi/code-mix). Configurable via `SAATHI_TTS_SPEAKER`.
- `model` — `bulbul:v2`.
- `speech_sample_rate` — 8000 / 16000 / 22050. We use 22050 then transcode to
  OGG/Opus for WhatsApp.

## Response (observed)

```json
{ "request_id": "...", "audios": ["<base64 WAV>"] }
```

- `audios[i]` is **base64-encoded WAV** (RIFF header confirmed: `b'RIFF'`; the
  "Namaste" probe returned 16 940 bytes). One entry per `inputs` element.
- `request_id` — used as the ledger event's `request_id` for dedupe, mirroring
  STT.

## Pipeline we wrap it in

    reply text -> chunk -> Sarvam TTS -> base64 WAV(s) -> concat PCM -> one WAV
              -> speech.audio.wav_to_ogg_opus -> wa.upload_media -> wa.send_audio

## Notes / unknowns

- **Pricing not captured.** Sarvam bills TTS per character; the exact paise/char
  is not in any doc we hold. The ledger records the durable truth (character
  count) and an *estimate* (`SAATHI_SARVAM_TTS_PAISE_PER_1K_CHARS`,
  `cost_source="catalog_estimate"`). Reconcile against a real invoice — same way
  STT pricing was added after the fact (PR #31). Tracked in `USAGE_LEDGER.md`.
- Streaming and the WebSocket API exist but are not used; the REST batch call
  above is enough for short elder replies.

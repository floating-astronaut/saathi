# STT corpus manifest schema

One JSON file per sample, alongside its audio, in this directory. Rationale and
the collection/consent protocol: [`docs/STT_EVAL.md`](../../docs/STT_EVAL.md).

```json
{
  "id": "hi-001",
  "audio": "hi-001.ogg",
  "lang": "hi-IN",
  "reference": "Roz subah aath baje Amlong ki goli aur raat ko Glycomet",
  "entities": [
    {"text": "Amlong",    "type": "medicine"},
    {"text": "Glycomet",  "type": "medicine"},
    {"text": "aath baje", "type": "time"}
  ],
  "conditions": ["tv_background", "elder", "code_mixed"],
  "consent": "consent-ref-2026-07-30-hi-001",
  "notes": "speaker restarts once mid-sentence"
}
```

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique sample id. |
| `audio` | yes | Filename (relative to this dir) of the recording. `.ogg`/`.opus`/`.wav`. |
| `lang` | yes | Sarvam language code, e.g. `hi-IN`, `en-IN`. |
| `reference` | yes | Hand transcript in the **script the STT mode emits** (`indic-en` → Latin), so it is comparable to the model output. |
| `entities` | recommended | Tokens that had to survive. `type` ∈ `medicine, time, date, person, place, number`. Multi-word entities require every significant word to survive. |
| `conditions` | recommended | Free-form tags to slice results: `clean`, `tv_background`, `child_shouting`, `bad_line`, `elder`, `fast`, `code_mixed`, … |
| `consent` | yes (DPDP) | Reference to the recorded consent for this speaker's audio. Not the consent text. |
| `notes` | no | Anything useful for a human reading a miss. |

**Do not commit real samples here.** This directory is git-ignored except for
its README and this schema. Keep the corpus out of band (access-controlled
storage) and point the harness at it with `--corpus`.

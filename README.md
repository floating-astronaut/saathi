# Saathi

WhatsApp-native, voice-first assistant for older adults in India.
Remembers, reminds, searches, assembles — and never transacts.

Docs of record live outside this repo for now:
`PRD-whatsapp-elder-agent.md` (research) and `PLAN-whatsapp-elder-agent-v1.md`
(build plan, decisions, measurements).

## Layout

    saathi/web/      FastAPI: webhook + healthz
    saathi/wa/       Cloud API client; window.py is the 24h gate (plan G2)
    saathi/speech/   Sarvam Saaras v3 STT, TTS iface, ffmpeg transcode
    saathi/agent/    tool loop + tools (memory, reminders, cart)
    saathi/safety/   deterministic pre-LLM classifier
    saathi/worker/   reminder scheduler (Postgres SKIP LOCKED), TTL jobs
    db/schema.sql    schema
    evals/           Hinglish entity-accuracy corpus + scorer

## Decisions already made (see plan)

* Channel: Meta Cloud API **direct**, no BSP.
* Host: AWS **559896294326**, **ap-south-1**, box `i-01b2c27883acb25ca`, SSM-only.
* Model: **`zai.glm-5`** on Bedrock ap-south-1 — regional endpoint, so inference
  stays in India. Scored 8/8 on Hinglish time+medicine extraction where the
  cheaper models scored 3–7/8.
* **No prompt caching** (unsupported for this model). Cost is linear in prompt
  size instead, so the system prompt + tools + fact block has a hard budget:
  `SAATHI_PREFIX_TOKEN_BUDGET=3000`.
* Flights/Duffel cut from v1.

## Local

    uv sync
    createdb saathi && psql -d saathi -f db/schema.sql
    uv run uvicorn saathi.web.app:app --port 3130

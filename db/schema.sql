-- Saathi v1 schema. PostgreSQL 18.
--
-- Design notes that are load-bearing (see PLAN-whatsapp-elder-agent-v1.md):
--   * Postgres is the store AND the job queue. No Redis.
--   * `sessions.window_expires_at` makes WhatsApp's 24-hour window first-class,
--     so the send layer can physically refuse free-form outside it (plan G2).
--   * `reminders` (recurrence definition) is split from `reminder_fires` (queue
--     rows). Ack/snooze/nudge is then a state machine on one table, and the
--     §15 acknowledgement-rate metric falls out for free.
--   * `llm_calls.prefix_tokens` exists because we chose a model with no prompt
--     caching (plan §5c): cost is now linear in prompt size, and you cannot
--     hold a 3k-token prefix budget you do not measure.
--   * Soft delete via `deleted_at` everywhere a DPDP erasure has to reach.

begin;

create extension if not exists pg_trgm;      -- fuzzy match for entity correction (§10)

-- ---------------------------------------------------------------- users

create table if not exists users (
    id                bigserial primary key,
    wa_id             text not null unique,          -- WhatsApp sender id (E.164 digits)
    display_name      text,
    lang_pref         text not null default 'hi-en', -- D2: Hindi + English, code-mixed
    tz                text not null default 'Asia/Kolkata',
    voice_reply_pref  text not null default 'auto'   -- auto|always|never  (D4)
                      check (voice_reply_pref in ('auto', 'always', 'never')),
    onboarded_at      timestamptz,
    consent_at        timestamptz,
    consent_version   text,
    paused            boolean not null default false,
    created_at        timestamptz not null default now(),
    deleted_at        timestamptz
);

-- The 24-hour customer-service window (§11). One row per user, upserted on
-- every inbound message. The send layer reads this before choosing free-form
-- vs template; see saathi/wa/window.py.
create table if not exists sessions (
    user_id           bigint primary key references users(id) on delete cascade,
    last_inbound_at   timestamptz not null,
    window_expires_at timestamptz not null,
    updated_at        timestamptz not null default now()
);

-- ---------------------------------------------------------------- messages

do $$ begin
    create type msg_direction as enum ('in', 'out');
exception when duplicate_object then null; end $$;

do $$ begin
    create type msg_kind as enum ('text', 'audio', 'image', 'interactive', 'template', 'system');
exception when duplicate_object then null; end $$;

create table if not exists messages (
    id                bigserial primary key,
    user_id           bigint not null references users(id) on delete cascade,
    direction         msg_direction not null,
    kind              msg_kind not null,
    -- unique so a replayed webhook is a no-op: Meta retries aggressively
    wa_message_id     text unique,
    body_text         text,
    transcript        text,          -- post-correction (§10)
    transcript_raw    text,          -- straight out of STT, kept for eval scoring
    stt_ms            integer,
    template_name     text,
    meta              jsonb not null default '{}'::jsonb,
    created_at        timestamptz not null default now()
);

create index if not exists messages_user_time on messages (user_id, created_at desc);

-- ---------------------------------------------------------------- memory (C1)

do $$ begin
    create type fact_kind as enum
        ('person', 'medicine', 'place', 'brand', 'preference', 'routine', 'other');
exception when duplicate_object then null; end $$;

-- Facts are written explicitly by a tool call, never inferred into an opaque
-- blob. `surface_forms` is the entity-bias vocabulary handed to STT and to the
-- correction pass — this is the higher-value use of memory (§10), and it is why
-- the product hears the user better the longer they use it.
create table if not exists facts (
    id                bigserial primary key,
    user_id           bigint not null references users(id) on delete cascade,
    kind              fact_kind not null default 'other',
    key               text not null,
    value             text not null,
    surface_forms     text[] not null default '{}',
    source_message_id bigint references messages(id) on delete set null,
    confidence        real not null default 1.0,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    deleted_at        timestamptz
);

create unique index if not exists facts_user_key
    on facts (user_id, kind, key) where deleted_at is null;
create index if not exists facts_value_trgm on facts using gin (value gin_trgm_ops);

-- ---------------------------------------------------------------- reminders (C2)

create table if not exists reminders (
    id           bigserial primary key,
    user_id      bigint not null references users(id) on delete cascade,
    title        text not null,
    rrule        text,                        -- null => one-off
    tz           text not null default 'Asia/Kolkata',
    next_fire_at timestamptz,
    status       text not null default 'active'
                 check (status in ('active', 'paused', 'done', 'cancelled')),
    created_at   timestamptz not null default now(),
    deleted_at   timestamptz
);

do $$ begin
    create type fire_state as enum
        ('pending', 'sent', 'acked', 'snoozed', 'nudged', 'failed', 'skipped');
exception when duplicate_object then null; end $$;

create table if not exists reminder_fires (
    id            bigserial primary key,
    reminder_id   bigint not null references reminders(id) on delete cascade,
    user_id       bigint not null references users(id) on delete cascade,
    scheduled_for timestamptz not null,
    state         fire_state not null default 'pending',
    attempts      integer not null default 0,
    sent_at       timestamptz,
    wa_message_id text,
    acked_at      timestamptz,
    snoozed_to    timestamptz,
    nudge_sent_at timestamptz,
    last_error    text,
    created_at    timestamptz not null default now()
);

-- Partial index: the worker's claim query touches only the pending tail,
-- so it stays index-only however large the history grows.
create index if not exists reminder_fires_due
    on reminder_fires (scheduled_for) where state = 'pending';
-- Materialising the same occurrence twice would double-message an elder.
create unique index if not exists reminder_fires_dedupe
    on reminder_fires (reminder_id, scheduled_for);

-- ---------------------------------------------------------------- media (§13)

create table if not exists media_blobs (
    id           bigserial primary key,
    user_id      bigint not null references users(id) on delete cascade,
    message_id   bigint references messages(id) on delete set null,
    storage_key  text not null,
    bytes        integer,
    mime         text,
    delete_after timestamptz not null,   -- hard TTL, proposal 7 days
    deleted_at   timestamptz,
    created_at   timestamptz not null default now()
);

create index if not exists media_blobs_expiry
    on media_blobs (delete_after) where deleted_at is null;

-- ---------------------------------------------------------------- safety (§12)

create table if not exists safety_events (
    id         bigserial primary key,
    user_id    bigint references users(id) on delete set null,
    message_id bigint references messages(id) on delete set null,
    trigger    text not null
               check (trigger in ('medical_emergency', 'self_harm', 'medical_advice', 'scam')),
    matched    text,
    action     text not null,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- consent & erasure (§13)

create table if not exists consent_log (
    id         bigserial primary key,
    user_id    bigint not null references users(id) on delete cascade,
    version    text not null,
    lang       text not null,
    granted    boolean not null,
    created_at timestamptz not null default now()
);

create table if not exists erasure_requests (
    id           bigserial primary key,
    user_id      bigint not null references users(id) on delete cascade,
    state        text not null default 'pending'
                 check (state in ('pending', 'running', 'done', 'failed')),
    requested_at timestamptz not null default now(),
    completed_at timestamptz,
    note         text
);

-- ---------------------------------------------------------------- instrumentation

-- Cost is linear in prompt size now (no caching), so prefix_tokens is a budget
-- line, not a curiosity. turn_kind exists to answer risk R6 from day one:
-- if 'chat' turns dominate 'task' turns, the product is telling you something.
create table if not exists llm_calls (
    id            bigserial primary key,
    user_id       bigint references users(id) on delete set null,
    message_id    bigint references messages(id) on delete set null,
    model         text not null,
    turn_kind     text not null default 'task' check (turn_kind in ('task', 'chat')),
    prefix_tokens integer,
    input_tokens  integer,
    output_tokens integer,
    latency_ms    integer,
    tool_name     text,
    created_at    timestamptz not null default now()
);

create index if not exists llm_calls_time on llm_calls (created_at desc);

commit;

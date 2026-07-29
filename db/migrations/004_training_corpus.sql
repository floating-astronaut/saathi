-- 004: opt-in, derived training corpus.
--
-- We do not store conversations for training. This table holds *derived* pairs
-- only — how a word was misheard, what shape an utterance had — never
-- transcripts, never person or place names.
--
-- Under DPDP, improving the model is a different purpose from providing the
-- service, so it needs its own consent. Bundling it into onboarding consent
-- would not be "free, specific and informed", and the vocabulary here is
-- health-adjacent.

begin;

create table if not exists training_consent (
    user_id    bigint primary key references users(id) on delete cascade,
    granted    boolean not null,
    version    text not null,
    granted_at timestamptz not null default now(),
    revoked_at timestamptz
);

do $$ begin
    create type training_kind as enum ('asr_correction', 'clock_word', 'slot_shape');
exception when duplicate_object then null; end $$;

create table if not exists training_samples (
    id          bigserial primary key,
    -- FK with cascade on purpose: erasure must remove these too, so a user who
    -- says "forget everything about me" is not still in the corpus.
    user_id     bigint not null references users(id) on delete cascade,
    kind        training_kind not null,
    input       text not null,     -- what was heard / said (token or shape)
    output      text not null,     -- what it should have been
    lang        text not null default 'hi-en',
    created_at  timestamptz not null default now()
);

create index if not exists training_samples_pair on training_samples (kind, input, output);
create index if not exists training_samples_user on training_samples (user_id);

-- The ONLY sanctioned export path. A pair leaves the box only once at least 5
-- distinct users have produced it, which is what turns "a medicine this person
-- takes" into "a word Indian ASR mishears".
create or replace view training_export as
select kind, input, output, lang,
       count(distinct user_id) as n_users,
       count(*)                as n_samples,
       min(created_at)         as first_seen,
       max(created_at)         as last_seen
  from training_samples
 group by kind, input, output, lang
having count(distinct user_id) >= 5;

commit;

-- 013: Persistent, content-free reservations for PR-15 inbound admission.
--
-- This is intentionally separate from messages: audio is logged only after
-- transcription, which is too late to stop a concurrent STT spend burst.

begin;

create table if not exists inbound_turn_admissions (
    id          bigserial primary key,
    user_id     bigint not null references users(id) on delete cascade,
    admitted_at timestamptz not null default now()
);
create index if not exists inbound_turn_admissions_user_time
    on inbound_turn_admissions (user_id, admitted_at desc);

create table if not exists inbound_limit_notices (
    user_id          bigint not null references users(id) on delete cascade,
    reason           text not null check (reason in ('rate_limit', 'busy')),
    last_notified_at timestamptz not null default now(),
    primary key (user_id, reason)
);

commit;

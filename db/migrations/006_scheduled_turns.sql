-- 006: one queue for all scheduled work, not a reminder-shaped one.
--
-- reminder_fires knew about reminders specifically. Nudges, daily check-ins and
-- dormancy re-verification are all specced, and each would have added a branch
-- to the worker — the same if/elif shape we removed from the inbound path.
--
-- scheduled_turns is the general queue: a kind, a payload, a due time. The
-- worker claims due rows and dispatches by kind to a registered handler. Adding
-- a new kind of scheduled work touches no existing code.
--
-- reminder_fires is kept and its rows are copied across, because the reminder
-- ack/snooze state machine and the §15 acknowledgement metric read from it.
-- New work goes to scheduled_turns only.

begin;

do $$ begin
    create type turn_state as enum
        ('pending', 'sent', 'acked', 'snoozed', 'failed', 'skipped');
exception when duplicate_object then null; end $$;

create table if not exists scheduled_turns (
    id            bigserial primary key,
    user_id       bigint not null references users(id) on delete cascade,
    -- Registered kind: 'reminder', 'nudge', 'checkin', 'reverify', …
    -- Deliberately text rather than an enum: adding a kind should not need a
    -- migration, which is the whole point of the generalisation.
    kind          text not null,
    payload       jsonb not null default '{}'::jsonb,
    scheduled_for timestamptz not null,
    state         turn_state not null default 'pending',
    attempts      integer not null default 0,
    -- Idempotency for schedulers that may enqueue the same occurrence twice.
    dedupe_key    text,
    sent_at       timestamptz,
    wa_message_id text,
    acked_at      timestamptz,
    snoozed_to    timestamptz,
    last_error    text,
    created_at    timestamptz not null default now()
);

-- The claim query touches only the pending tail, whatever the history grows to.
create index if not exists scheduled_turns_due
    on scheduled_turns (scheduled_for) where state = 'pending';
create index if not exists scheduled_turns_user on scheduled_turns (user_id, kind);
create unique index if not exists scheduled_turns_dedupe
    on scheduled_turns (kind, dedupe_key) where dedupe_key is not null;

-- Carry existing reminder fires over so nothing due is dropped.
insert into scheduled_turns (user_id, kind, payload, scheduled_for, state,
                             attempts, dedupe_key, sent_at, wa_message_id, acked_at)
select f.user_id, 'reminder',
       jsonb_build_object('reminder_id', f.reminder_id, 'fire_id', f.id),
       f.scheduled_for, f.state::text::turn_state, f.attempts,
       'fire:' || f.id, f.sent_at, f.wa_message_id, f.acked_at
  from reminder_fires f
 where not exists (select 1 from scheduled_turns s
                    where s.kind = 'reminder' and s.dedupe_key = 'fire:' || f.id)
on conflict do nothing;

commit;

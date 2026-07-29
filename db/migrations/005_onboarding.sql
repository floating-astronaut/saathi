-- 005: self-serve onboarding.
--
-- Replaces the pairing gate as the default path: anyone may start by messaging
-- the number. That is safe because onboarding is a *deterministic* state
-- machine — no model call until the person has consented and finished — so an
-- unknown or hostile sender costs us nothing but a few templated replies.
--
-- It is also better for the user. PRD §6.6: prefer buttons over free text
-- wherever a choice is bounded. Onboarding is entirely bounded choices, so an
-- elder never has to guess the magic phrasing to get started.

begin;

do $$ begin
    create type onboarding_state as enum (
        'new',        -- never spoken to us
        'consent',    -- asked for consent, waiting
        'name',       -- confirming what to call them
        'reminders',  -- D3: reminders are opt-in, asked here
        'improve',    -- optional, separate training consent
        'done'
    );
exception when duplicate_object then null; end $$;

alter table users add column if not exists onboarding onboarding_state not null default 'new';
alter table users add column if not exists onboarded_via text;

-- Everyone who already exists predates onboarding and should not be dropped
-- back into it.
update users set onboarding = 'done' where onboarding = 'new' and created_at < now();

commit;

-- 012: operator backfill for every existing account, including mid-onboarding.
--
-- The steady-state trigger still fires when onboarding completes. This migration
-- is a one-time correction for the accounts that already exist today: the
-- operator's session goal is that the current 6-7 users all have their own
-- capped key, not only the subset whose onboarding reached `done` before this
-- deploy.
--
-- Versioned again because `scheduled_turns` dedupe keys are permanent history.

begin;

insert into scheduled_turns (user_id, kind, payload, scheduled_for, dedupe_key)
select u.id,
       'provision_key',
       jsonb_build_object('account_id', a.id),
       now(),
       'provision:v3:' || a.id
  from accounts a
  join users u on u.account_id = a.id
 where a.deleted_at is null
   and not exists (
       select 1 from ai_keys k
        where k.account_id = a.id
          and k.provider = 'openrouter'
          and k.status = 'active')
   and not exists (
       select 1 from scheduled_turns s
        where s.kind = 'provision_key'
          and s.dedupe_key = 'provision:v3:' || a.id)
on conflict do nothing;

commit;

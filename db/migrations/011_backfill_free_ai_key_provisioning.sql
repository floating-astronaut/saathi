-- 011: queue per-account AI key provisioning for accounts that predate the trigger.
--
-- Onboarding queues `provision_key` when it completes, but the first live users
-- completed onboarding before that trigger existed. Migration 010 also revoked a
-- beta-reset key locally after correcting backfilled accounts to `free`, but it
-- did not enqueue the replacement it described.
--
-- The dedupe key is versioned (`provision:v2:<account_id>`) because
-- `scheduled_turns` keeps `(kind, dedupe_key)` unique forever, even after an old
-- provision row is acked or failed. Reusing `provision:<account_id>` would make a
-- corrected retry silently disappear.

begin;

insert into scheduled_turns (user_id, kind, payload, scheduled_for, dedupe_key)
select u.id,
       'provision_key',
       jsonb_build_object('account_id', u.account_id),
       now(),
       'provision:v2:' || u.account_id
  from users u
  join accounts a on a.id = u.account_id and a.deleted_at is null
 where u.onboarding = 'done'
   and not exists (
       select 1 from ai_keys k
        where k.account_id = u.account_id
          and k.provider = 'openrouter'
          and k.status = 'active')
   and not exists (
       select 1 from scheduled_turns s
        where s.kind = 'provision_key'
          and s.dedupe_key = 'provision:v2:' || u.account_id)
on conflict do nothing;

commit;

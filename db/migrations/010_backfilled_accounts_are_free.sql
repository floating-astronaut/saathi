-- 010: the backfilled accounts were given a renewing allowance by mistake.
--
-- Migration 008 backfilled every pre-existing user's account as `beta`. That was
-- written before D-T, which made `free` the universal one-time grant and left
-- `beta` as the tier an operator hands a tester **and which renews monthly**.
-- The backfill was never revisited, so six live accounts carried a renewing $5
-- rather than $5 once.
--
-- Not theoretical. A key was minted from one of them on 2026-07-27 at 22:39 and
-- exists at OpenRouter as `saathi:account:6:plan:beta:env:dev` with
-- `limit_reset: monthly`. Because routing is BYOK onto our own Bedrock
-- credential, that spend is real money on our AWS bill rather than an
-- OpenRouter balance — so this is a live billing defect, not a latent one.
--
-- 008 is deliberately **not** edited: it is recorded in `schema_migrations` with
-- its checksum, and changing it would abort the next deploy with CHECKSUM
-- MISMATCH. That guard is PR-25 working, and the right response to it is a new
-- migration rather than a quiet rewrite of history.
--
-- Only the backfilled rows are touched. An account an operator deliberately
-- promoted to `beta` keeps it — the label is the discriminator, and it is the
-- one 008 wrote.

begin;

update accounts
   set tier = 'free'::account_tier
 where tier = 'beta'
   and label like 'backfill: user %';

-- The key minted under the wrong tier keeps a monthly reset that no `free`
-- account should have. Mark it revoked so the next `provision_key` turn mints a
-- correct one; the upstream key must be deleted separately, because this
-- migration cannot reach OpenRouter and a row that claims a key is gone while it
-- still bills would be worse than the bug it fixes.
update ai_keys
   set status = 'revoked', revoked_at = now()
 where status = 'active'
   and name like '%:plan:beta:%'
   and account_id in (select id from accounts where label like 'backfill: user %');

insert into ai_key_events (account_id, action, outcome, detail)
select account_id, 'revoke', 'ok',
       'migration 010: minted under beta by the 008 backfill; tier corrected to free'
  from ai_keys
 where status = 'revoked' and revoked_at >= now() - interval '1 minute';

commit;

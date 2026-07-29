-- ID-2: a WhatsApp handle is a revocable claim, not an account.  After sixty
-- days of silence we ask it to speak before it is ever trusted again; after
-- ninety days of continued silence we revoke the claim.  The user, facts and
-- reminders remain intact for a verified move to a new handle.

begin;

alter type channel_status add value if not exists 'reverify';

-- Existing live handles need their first 60-day check.  The permanent dedupe
-- key includes the observed last_seen value: a later confirmation schedules a
-- new occurrence rather than colliding with historical queue evidence.
insert into scheduled_turns (user_id, kind, payload, scheduled_for, dedupe_key)
select c.user_id,
       'reverify',
       jsonb_build_object('user_channel_id', c.id, 'stage', 'warn'),
       c.last_seen_at + interval '60 days',
       'reverify:warn:' || c.id || ':' || extract(epoch from c.last_seen_at)::bigint
  from user_channels c
 where c.revoked_at is null
   and c.status = 'active'
   and not exists (
       select 1 from scheduled_turns s
        where s.kind = 'reverify'
          and s.dedupe_key = 'reverify:warn:' || c.id || ':' || extract(epoch from c.last_seen_at)::bigint
   )
on conflict do nothing;

commit;

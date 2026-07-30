-- 016: Click-to-WhatsApp (CTWA) attribution (CAPI-1).
-- Meta puts a `ctwa_clid` on the first message of a conversation that began with
-- an "ads that click to WhatsApp" tap. Capturing it lets onboarding completion be
-- reported to the Conversions API so Meta can attribute the signup to the ad.
--
-- Content-free by construction: a click id Meta itself minted, plus the time we
-- first saw it. Nothing about the person's messages, and no PII — with CTWA the
-- click id is the match key, so attribution needs nothing about the elder.
-- Write-once in application code (set only while null), so a later ad click does
-- not overwrite the one that actually started the relationship.

begin;

alter table users
    add column if not exists ctwa_clid        text,
    add column if not exists ctwa_captured_at  timestamptz;

commit;

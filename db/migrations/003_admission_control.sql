-- 003: admission control.
--
-- Pattern borrowed from OpenClaw's `channels.<name>.dmPolicy: pairing | open`:
-- an unknown sender on a DM channel is NOT processed until approved.
--
-- Saathi needs this more than a general assistant does:
--   * cost — an unknown sender otherwise gets a free LLM turn and STT minutes
--   * safety — an eldercare agent should not converse with arbitrary strangers
--   * D1/R5 — the adult child onboards the elder, so we *know in advance* which
--     number should arrive. Anyone else is noise or abuse, not a user.
--
-- Deliberately not silent: an unknown sender gets one short, non-hostile reply
-- explaining what to do. Refusing without explanation is exactly the "confusing
-- digital tool" this product exists to avoid.

begin;

do $$ begin
    create type channel_status as enum ('pending', 'active', 'blocked');
exception when duplicate_object then null; end $$;

alter table user_channels add column if not exists status channel_status not null default 'active';

-- Rate-limit the unknown-sender reply so a hostile number cannot make us send
-- (and pay for) unlimited messages by messaging repeatedly.
alter table user_channels add column if not exists admission_replies int not null default 0;
alter table user_channels add column if not exists admission_last_at timestamptz;

create index if not exists user_channels_pending
    on user_channels (channel, created_at) where status = 'pending';

-- Existing handles predate the policy and are known-good.
update user_channels set status = 'active' where status = 'pending';

commit;

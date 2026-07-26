-- 002: identity, channels, conversations, and message lifecycle.
--
-- Three problems solved together, because they are the same problem:
--
--   1. There is no login. Auth is "you control this handle on this channel."
--   2. A phone number is NOT a person. India permits recycling a disconnected
--      number after ~90 days. Binding identity to the number means a recycled
--      number inherits an elder's medicines, doctor and family. Identity is
--      therefore its own row; a handle is a *verified claim* on it, and a claim
--      can go stale.
--   3. WhatsApp is one transport, not the product. Telegram/Discord/RCS should
--      be additive, and a person who moves channel keeps their memory.
--
-- Persistence model: our store is the source of truth, deliberately independent
-- of the client. WhatsApp deletions are client-side and Meta does not notify us,
-- so a user "deleting the chat" on their phone changes nothing here. That is the
-- ChatGPT property the operator asked for -- state lives server-side and follows
-- the person, not the device. The counterweight is that deletion must therefore
-- be a first-class action *in* the product (see messages.deleted_at and the
-- forget_everything tool), because we have removed the user's usual way to do it.

begin;

-- ---------------------------------------------------------------- channels

do $$ begin
    create type channel_kind as enum ('whatsapp', 'telegram', 'discord', 'sms', 'web');
exception when duplicate_object then null; end $$;

-- A verified handle on some channel, pointing at a user (the identity).
-- `users` remains the identity row; this table is how someone proves they are it.
create table if not exists user_channels (
    id               bigserial primary key,
    user_id          bigint not null references users(id) on delete cascade,
    channel          channel_kind not null,
    -- Channel-native id: WhatsApp wa_id, Telegram user id, Discord snowflake.
    -- NOT necessarily the phone number -- wa_id and E.164 diverge in some
    -- countries, so we keep both rather than assuming they are the same string.
    channel_user_id  text not null,
    phone_e164       text,
    display_name     text,
    is_primary       boolean not null default false,
    verified_at      timestamptz,
    -- Recycling defence: how recently we had evidence this handle is still the
    -- same human. Long silence + a fresh inbound is a re-verification trigger,
    -- not a welcome back.
    last_seen_at     timestamptz not null default now(),
    revoked_at       timestamptz,
    created_at       timestamptz not null default now()
);

-- One live claim per handle. A revoked claim frees the handle for someone else,
-- which is exactly what number recycling requires.
create unique index if not exists user_channels_handle
    on user_channels (channel, channel_user_id) where revoked_at is null;
create index if not exists user_channels_user on user_channels (user_id);
create unique index if not exists user_channels_one_primary
    on user_channels (user_id) where is_primary and revoked_at is null;

-- Linking a second channel to an existing identity: a short code delivered on
-- the channel already trusted, redeemed on the new one. Never link on a name or
-- phone-number match alone.
create table if not exists channel_link_codes (
    code        text primary key,
    user_id     bigint not null references users(id) on delete cascade,
    channel     channel_kind not null,
    expires_at  timestamptz not null,
    consumed_at timestamptz,
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------- conversations

-- A continuous thread on one channel. Memory and facts are per *user* and cross
-- channels; a conversation is per channel, because transcripts are.
create table if not exists conversations (
    id              bigserial primary key,
    user_id         bigint not null references users(id) on delete cascade,
    channel         channel_kind not null,
    started_at      timestamptz not null default now(),
    last_message_at timestamptz not null default now(),
    closed_at       timestamptz
);
create index if not exists conversations_user on conversations (user_id, last_message_at desc);

-- ---------------------------------------------------------------- messages

alter table messages add column if not exists channel channel_kind not null default 'whatsapp';
alter table messages add column if not exists conversation_id bigint references conversations(id) on delete set null;
alter table messages add column if not exists user_channel_id bigint references user_channels(id) on delete set null;
-- Deletion is a product action, not a client one:
--   deleted_at  -> hidden from the user and from prompt context
--   redacted_at -> content actually removed, row kept so counts and the audit
--                  trail survive. DPDP erasure hard-deletes instead.
alter table messages add column if not exists deleted_at timestamptz;
alter table messages add column if not exists redacted_at timestamptz;

create index if not exists messages_conversation
    on messages (conversation_id, created_at desc) where deleted_at is null;

-- ---------------------------------------------------------------- backfill

-- Every existing user reached us over WhatsApp, so give each one a verified
-- primary handle from the wa_id they already have.
insert into user_channels (user_id, channel, channel_user_id, phone_e164,
                           display_name, is_primary, verified_at, last_seen_at)
select u.id, 'whatsapp', u.wa_id, u.wa_id, u.display_name, true, now(), now()
  from users u
 where not exists (select 1 from user_channels c
                    where c.user_id = u.id and c.channel = 'whatsapp')
on conflict do nothing;

commit;

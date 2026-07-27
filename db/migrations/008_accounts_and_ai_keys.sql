-- 008: the account tenant, and the per-account AI keys that hang off it.
--
-- Until now the closest thing to a tenant was `users`, which is really a person
-- reached through a handle. AI_ROUTING.md §4 argues the tenant must never be the
-- handle: India recycles phone numbers after ~90 days, minting upstream keys is
-- rate-limited and would sit on a path an elder is waiting on, and every number
-- change would strand a key. So spend is attributed to an *account*, and a
-- handle is the revocable way you reach it.
--
-- For beta each tester is their own account. The shape still has to be right
-- now, because keys get minted against these ids and an id you have already
-- given to a vendor is not one you can quietly redefine later.
--
-- Backfill: every existing user gets their own account, which preserves today's
-- one-person-one-household reality without asserting it forever.
--
-- NOTE this migration is idempotent and its backfill is guarded, because
-- PR-25's ledger is what stops a re-run and the ledger is younger than some of
-- these databases. A backfill that runs twice here would mint a second account
-- per user and orphan the first.

begin;

do $$ begin
    -- Unknown tier must resolve to the *lowest* cap, never the highest, so the
    -- enum is ordered deliberately and `free` is first.
    create type account_tier as enum ('free', 'beta', 'paid');
exception when duplicate_object then null; end $$;

create table if not exists accounts (
    id          bigserial primary key,
    tier        account_tier not null default 'free',
    label       text,                      -- human note: "Sonia, Pune beta"
    created_at  timestamptz not null default now(),
    deleted_at  timestamptz
);

alter table users add column if not exists account_id bigint references accounts(id);

-- One account per existing user, once. The `where account_id is null` guard is
-- what makes re-running this safe: 003 and 005 taught us that a backfill which
-- re-runs is not a backfill, it is a corruption with good intentions.
insert into accounts (tier, label)
select 'beta'::account_tier, 'backfill: user ' || u.id
  from users u
 where u.account_id is null;

update users u
   set account_id = a.id
  from accounts a
 where a.label = 'backfill: user ' || u.id
   and u.account_id is null;

create index if not exists users_account_idx on users(account_id);

-- --- the minted keys ---------------------------------------------------------
--
-- `key_ciphertext` is Fernet, never a plaintext. `key_hash` is OpenRouter's
-- own hash and is the ONLY handle by which a key can be rotated or revoked —
-- AI_ROUTING.md §5 carries a fallback re-read specifically because losing it
-- means the key can never be cleaned up.
--
-- `name` carries the `saathi:` prefix guard. This OpenRouter org also holds
-- MeshPilot's keys and DELETE works on all of them, so the prefix is asserted
-- in code before any list, revoke or sync — and stored here so an operator
-- staring at the dashboard during an incident can join a key back to a tenant.

create table if not exists ai_keys (
    id              bigserial primary key,
    account_id      bigint not null references accounts(id),
    provider        text not null default 'openrouter',
    name            text not null unique,
    key_hash        text,
    key_ciphertext  text not null,
    monthly_cap_usd numeric(10,2) not null,
    status          text not null default 'active'
                    check (status in ('active', 'revoked')),
    created_at      timestamptz not null default now(),
    revoked_at      timestamptz
);

-- Idempotency lives here, not in the application: exactly one active key per
-- account per provider, enforced by the database. "Calling twice mints once"
-- is then true even if two workers race, which is the only way it can actually
-- be true.
create unique index if not exists ai_keys_one_active_per_account
    on ai_keys(account_id, provider) where status = 'active';

-- --- the audit trail ---------------------------------------------------------
--
-- Written on BOTH outcomes, and on failure written *before* the error is
-- re-raised. "Did this account ever get a key, and why not" has to be
-- answerable months later, when the exception text is long gone.

create table if not exists ai_key_events (
    id          bigserial primary key,
    account_id  bigint not null references accounts(id),
    action      text not null check (action in ('mint', 'revoke')),
    outcome     text not null check (outcome in ('ok', 'error')),
    detail      text,
    created_at  timestamptz not null default now()
);

create index if not exists ai_key_events_account_idx
    on ai_key_events(account_id, created_at desc);

commit;

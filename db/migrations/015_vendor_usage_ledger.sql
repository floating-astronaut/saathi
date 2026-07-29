-- 015: Saathi-owned, content-free vendor usage ledger (LEDGER-1).
-- Reservations are committed before a paid call in later slices; events are
-- append-only accounting facts. Neither table stores user content or secrets.

begin;

create type vendor_usage_status as enum ('success', 'error', 'skipped', 'rate_limited');
create type usage_reservation_state as enum ('held', 'settled', 'released', 'expired');

create table vendor_usage_reservations (
    id bigserial primary key,
    idempotency_key text not null unique,
    user_id bigint references users(id) on delete set null,
    account_id bigint references accounts(id) on delete set null,
    vendor text not null,
    service text not null,
    operation text not null,
    currency text not null default 'USD',
    reserved_minor bigint not null check (reserved_minor >= 0),
    actual_minor bigint check (actual_minor is null or actual_minor >= 0),
    state usage_reservation_state not null default 'held',
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    settled_at timestamptz,
    released_at timestamptz
);
create index vendor_usage_reservations_active
    on vendor_usage_reservations (account_id, created_at)
    where state = 'held';

create table vendor_usage_events (
    id bigserial primary key,
    created_at timestamptz not null default now(),
    user_id bigint references users(id) on delete set null,
    account_id bigint references accounts(id) on delete set null,
    reservation_id bigint references vendor_usage_reservations(id) on delete set null,
    vendor text not null,
    service text not null,
    operation text not null,
    model text,
    request_id text,
    status vendor_usage_status not null,
    units jsonb not null default '{}',
    cost jsonb not null default '{}',
    cost_source text not null default 'unknown'
        check (cost_source in ('vendor_reported', 'catalog_estimate', 'unknown')),
    metadata jsonb not null default '{}',
    latency_ms integer check (latency_ms is null or latency_ms >= 0),
    error_code text
);
create index vendor_usage_events_user_time on vendor_usage_events (user_id, created_at desc);
create index vendor_usage_events_vendor_time on vendor_usage_events (vendor, service, created_at desc);
create unique index vendor_usage_events_request_once
    on vendor_usage_events (vendor, request_id) where request_id is not null;

commit;

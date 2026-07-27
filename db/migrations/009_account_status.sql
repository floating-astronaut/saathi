-- 009: an account can run out of its allowance, and say so.
--
-- D-T grants every user $5 once. Nothing modelled what happens when it is gone:
-- the key simply stopped authorising and the turn failed, which for the person
-- holding the phone is indistinguishable from the assistant breaking.
--
-- `status` is separate from `tier` on purpose. Tier is what you are entitled to;
-- status is where you are against it. Collapsing them would mean "exhausted" had
-- to be a tier, and then promoting someone to paid would lose the record of how
-- they got there.

begin;

alter table accounts add column if not exists status text not null default 'active'
    check (status in ('active', 'exhausted', 'paid'));

-- Set when the allowance ran out, so "how long were they stuck" is answerable.
alter table accounts add column if not exists exhausted_at timestamptz;
-- Set when payment cleared. Deliberately not a boolean: the date is what an
-- invoice dispute is argued with.
alter table accounts add column if not exists paid_at timestamptz;

-- Razorpay runs the collection itself and will not take money without a phone
-- number or email, so it — not us — holds the payer identity. What we need is
-- the join: our account id on one side, their customer id on the other, so a
-- captured payment can be credited to the right household without us ever
-- storing a card, a UPI handle or a contact detail we did not already have.
alter table accounts add column if not exists psp_customer_id text;
create unique index if not exists accounts_psp_customer_idx
    on accounts(psp_customer_id) where psp_customer_id is not null;

-- Payments are per-account and must reconcile against the gateway later, so the
-- reference the PSP gave us is stored rather than derived.
create table if not exists account_payments (
    id             bigserial primary key,
    account_id     bigint not null references accounts(id),
    amount_minor   bigint not null,          -- paise. Never a float.
    currency       text not null default 'INR',
    reference      text unique,              -- the PSP's id; unique stops double-credit
    status         text not null default 'pending'
                   check (status in ('pending', 'captured', 'failed')),
    created_at     timestamptz not null default now(),
    captured_at    timestamptz
);

create index if not exists account_payments_account_idx
    on account_payments(account_id, created_at desc);

commit;

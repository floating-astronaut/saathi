-- schema_migrations: which migrations this database has actually had applied.
--
-- Why this is not a file in db/migrations/: the ledger has to exist before the
-- first migration can be recorded, so a migration that created it would have to
-- record itself. It is deploy bookkeeping rather than application schema, so
-- the deployer owns it. ops/deploy.sh runs this file once per deploy, before
-- the migration loop. It is idempotent.
--
-- Why the ledger matters here and not only in principle: the migrations are
-- *not* all safely re-runnable, whatever the old comment in PROD_READINESS
-- assumed. 003 ends with
--     update user_channels set status = 'active' where status = 'pending';
-- and 005 with
--     update users set onboarding = 'done' where onboarding = 'new' ...
-- Re-running those admits every pending unknown sender and marks every
-- half-onboarded user as consented. They were correct once, as backfills. They
-- are wrong every time after.

-- This file runs on every deploy, so its steady state is "nothing to do".
-- Keep NOTICEs (create-if-not-exists chatter) out of the deploy log; warnings
-- and errors still come through.
set client_min_messages = warning;

begin;

create table if not exists schema_migrations (
    version    text primary key,          -- filename, e.g. 003_admission_control.sql
    checksum   text,                      -- sha256 of the file as applied; see below
    applied_at timestamptz not null default now(),
    origin     text not null default 'applied'
        check (origin in ('applied', 'baselined')),
    note       text
);

comment on column schema_migrations.checksum is
    'sha256 of the migration file at the moment it was applied. NULL on '
    'baselined rows: nobody watched those run, so we cannot claim to know '
    'which bytes went in.';

comment on column schema_migrations.origin is
    'applied  = ops/deploy.sh ran the file and saw it commit. '
    'baselined = the file predates this ledger; its effect was found already '
    'present in the database, but the run itself was never observed.';

-- ------------------------------------------------------------ baseline
--
-- 002..007 were applied to the ap-south-1 database long before this ledger
-- existed. They must not be re-run (see above) and they must not be marked
-- applied on faith either. So each one is claimed only if a *sentinel* — an
-- object that exists if and only if that file committed — is visible right
-- now. Each migration file is a single begin/commit, so the sentinel being
-- present means the whole file committed, not part of it.
--
-- Consequences worth knowing:
--   * On an empty database no sentinel matches, nothing is baselined, and
--     every migration runs normally.
--   * On a partially migrated database only the parts that really landed are
--     claimed; the rest run.
--   * A migration added after this ledger has no entry here, so it always
--     runs. Do not add one.
--
-- This block is inert once every database that matters has a ledger row per
-- migration, and can be deleted then.

insert into schema_migrations (version, checksum, origin, note)
select '002_identity_and_channels.sql', null, 'baselined',
       'pre-ledger: table user_channels present'
 where to_regclass('public.user_channels') is not null
   and not exists (select 1 from schema_migrations
                    where version = '002_identity_and_channels.sql');

insert into schema_migrations (version, checksum, origin, note)
select '003_admission_control.sql', null, 'baselined',
       'pre-ledger: column user_channels.status present'
 where exists (select 1 from information_schema.columns
                where table_schema = 'public' and table_name = 'user_channels'
                  and column_name = 'status')
   and not exists (select 1 from schema_migrations
                    where version = '003_admission_control.sql');

insert into schema_migrations (version, checksum, origin, note)
select '004_training_corpus.sql', null, 'baselined',
       'pre-ledger: table training_samples present'
 where to_regclass('public.training_samples') is not null
   and not exists (select 1 from schema_migrations
                    where version = '004_training_corpus.sql');

insert into schema_migrations (version, checksum, origin, note)
select '005_onboarding.sql', null, 'baselined',
       'pre-ledger: column users.onboarding present'
 where exists (select 1 from information_schema.columns
                where table_schema = 'public' and table_name = 'users'
                  and column_name = 'onboarding')
   and not exists (select 1 from schema_migrations
                    where version = '005_onboarding.sql');

insert into schema_migrations (version, checksum, origin, note)
select '006_scheduled_turns.sql', null, 'baselined',
       'pre-ledger: table scheduled_turns present'
 where to_regclass('public.scheduled_turns') is not null
   and not exists (select 1 from schema_migrations
                    where version = '006_scheduled_turns.sql');

insert into schema_migrations (version, checksum, origin, note)
select '007_hypoglycemia_trigger.sql', null, 'baselined',
       'pre-ledger: safety_events_trigger_check admits hypoglycemia'
 where exists (select 1 from pg_constraint
                where conrelid = to_regclass('public.safety_events')
                  and conname = 'safety_events_trigger_check'
                  and pg_get_constraintdef(oid) like '%hypoglycemia%')
   and not exists (select 1 from schema_migrations
                    where version = '007_hypoglycemia_trigger.sql');

commit;

-- Record one migration as applied. Run by ops/deploy.sh immediately after the
-- migration's own transaction commits:
--
--     psql "$DSN" -v ON_ERROR_STOP=1 -v ver=003_x.sql -v sum=<sha256> \
--          -f db/record_migration.sql
--
-- A plain insert, not an upsert: the deploy only gets here when the loop has
-- already established there is no row for this version. A conflict would mean
-- the ledger changed under us, and that should stop the deploy, not be papered
-- over.
insert into schema_migrations (version, checksum, origin)
values (:'ver', :'sum', 'applied');

-- Superuser-only. Run as `postgres`, separately from schema.sql, because
-- pg_trgm is not a trusted extension — the app role cannot create it.
create extension if not exists pg_trgm;

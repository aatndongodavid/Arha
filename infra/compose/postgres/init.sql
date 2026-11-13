-- Cluster level bootstrap, run once by the postgres superuser at first start.
-- Passwords come from the environment in staging and production (see infra/compose/*.yml).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'arha_owner') THEN
    CREATE ROLE arha_owner LOGIN PASSWORD 'arha_owner' NOSUPERUSER NOCREATEROLE NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'arha_app') THEN
    CREATE ROLE arha_app LOGIN PASSWORD 'arha_app' NOSUPERUSER NOCREATEROLE NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'arha_platform') THEN
    CREATE ROLE arha_platform LOGIN PASSWORD 'arha_platform' NOSUPERUSER NOCREATEROLE BYPASSRLS;
  END IF;
END $$;
-- The migration role may hand the narrow tenant resolver to the platform role (BYPASSRLS).
GRANT arha_platform TO arha_owner;
SELECT 'CREATE DATABASE arha OWNER arha_owner' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'arha')\gexec
SELECT 'CREATE DATABASE arha_test OWNER arha_owner' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'arha_test')\gexec

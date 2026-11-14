"""Drafts use `varName` (F-EDI-12). Published versions stay immutable; exports read both spellings.

Revision ID: 0004
"""
from alembic import op

revision = "0004"
down_revision = "0003"


def _exec_script(sql: str) -> None:
    dbapi_conn = op.get_bind().connection.dbapi_connection
    dbapi_conn.run_async(lambda conn: conn.execute(sql))  # type: ignore[union-attr]


def upgrade() -> None:
    # Run as the platform role would be required to bypass RLS; the owner runs migrations with RLS forced,
    # so the update goes through a SECURITY DEFINER helper owned by the platform role.
    _exec_script("""
CREATE OR REPLACE FUNCTION arha_rename_varname() RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  UPDATE forms SET draft_schema = replace(draft_schema::text, '"variableName"', '"varName"')::jsonb
  WHERE draft_schema::text LIKE '%"variableName"%';
$$;
GRANT CREATE ON SCHEMA public TO arha_platform;
ALTER FUNCTION arha_rename_varname() OWNER TO arha_platform;
REVOKE CREATE ON SCHEMA public FROM arha_platform;
SELECT arha_rename_varname();
DROP FUNCTION arha_rename_varname();
""")


def downgrade() -> None:
    pass

"""Procrastinate job queue schema (platform tables, no tenant data).

Revision ID: 0002
"""
from alembic import op
from procrastinate import schema

revision = "0002"
down_revision = "0001"

GRANTS = """
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO arha_app, arha_platform;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO arha_app, arha_platform;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO arha_app, arha_platform;
-- Re-apply the append-only rule on audit events.
REVOKE UPDATE, DELETE ON audit_events FROM arha_app;
"""


def _exec_script(sql: str) -> None:
    dbapi_conn = op.get_bind().connection.dbapi_connection
    dbapi_conn.run_async(lambda conn: conn.execute(sql))  # type: ignore[union-attr]


def upgrade() -> None:
    _exec_script(schema.SchemaManager.get_schema())
    _exec_script(GRANTS)


def downgrade() -> None:
    _exec_script("DROP TABLE IF EXISTS procrastinate_events, procrastinate_periodic_defers, "
                 "procrastinate_jobs, procrastinate_workers CASCADE")

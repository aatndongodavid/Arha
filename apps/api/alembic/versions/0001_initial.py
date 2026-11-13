"""Initial schema with row level security.

Revision ID: 0001
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None

SQL = Path(__file__).resolve().parents[1] / "sql" / "0001_initial.sql"


def _exec_script(sql: str) -> None:
    """Run a multi statement script with asyncpg's simple query protocol."""
    dbapi_conn = op.get_bind().connection.dbapi_connection
    dbapi_conn.run_async(lambda conn: conn.execute(sql))  # type: ignore[union-attr]


def upgrade() -> None:
    _exec_script(SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    _exec_script("DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION arha_owner;")

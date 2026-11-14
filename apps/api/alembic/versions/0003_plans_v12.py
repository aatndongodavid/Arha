"""Commercial grid v1.2: plan codes renamed, Pass Mémoire (student_passes), new payment purposes.

Revision ID: 0003
"""
from alembic import op

revision = "0003"
down_revision = "0002"

SQL = """
UPDATE organizations SET plan_code = 'decouverte' WHERE plan_code = 'discovery';
UPDATE organizations SET plan_code = 'equipe' WHERE plan_code = 'business';
UPDATE organizations SET plan_code = 'institution' WHERE plan_code = 'enterprise';
UPDATE subscriptions SET plan_code = 'equipe' WHERE plan_code = 'business';
ALTER TABLE organizations ALTER COLUMN plan_code SET DEFAULT 'decouverte';

ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_purpose_check;
ALTER TABLE payments ADD CONSTRAINT payments_purpose_check
  CHECK (purpose IN ('submission','subscription','pass','study'));

CREATE TABLE student_passes (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE DEFAULT app_org(),
  user_id uuid NOT NULL REFERENCES users(id),
  institution text NOT NULL CHECK (length(institution) BETWEEN 2 AND 200),
  level text NOT NULL CHECK (level IN ('licence','master','doctorat','autre')),
  amount bigint NOT NULL,
  currency char(3) NOT NULL,
  ambassador_code text CHECK (length(ambassador_code) <= 32),
  status text NOT NULL DEFAULT 'pending_payment' CHECK (status IN ('pending_payment','active','expired','canceled')),
  starts_at timestamptz,
  ends_at timestamptz,
  payment_id uuid REFERENCES payments(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_student_passes_active ON student_passes(ends_at) WHERE status = 'active';
ALTER TABLE student_passes ENABLE ROW LEVEL SECURITY;
ALTER TABLE student_passes FORCE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON student_passes USING (organization_id = app_org())
  WITH CHECK (organization_id = app_org());
GRANT SELECT, INSERT, UPDATE, DELETE ON student_passes TO arha_app, arha_platform;
"""


def _exec_script(sql: str) -> None:
    dbapi_conn = op.get_bind().connection.dbapi_connection
    dbapi_conn.run_async(lambda conn: conn.execute(sql))  # type: ignore[union-attr]


def upgrade() -> None:
    _exec_script(SQL)


def downgrade() -> None:
    _exec_script("""
DROP TABLE student_passes;
ALTER TABLE payments DROP CONSTRAINT payments_purpose_check;
ALTER TABLE payments ADD CONSTRAINT payments_purpose_check CHECK (purpose IN ('submission','subscription'));
UPDATE organizations SET plan_code = 'discovery' WHERE plan_code IN ('decouverte','pass_memoire');
UPDATE organizations SET plan_code = 'business' WHERE plan_code = 'equipe';
UPDATE organizations SET plan_code = 'enterprise' WHERE plan_code = 'institution';
ALTER TABLE organizations ALTER COLUMN plan_code SET DEFAULT 'discovery';
""")

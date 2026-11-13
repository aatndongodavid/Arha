-- Arha initial schema. Runs as arha_owner. Roles arha_app and arha_platform are created by
-- infra/compose/postgres/init.sql (cluster level). arha_app has no BYPASSRLS (rule 4).

CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION app_org() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.organization_id', true), '')::uuid
$$;
CREATE OR REPLACE FUNCTION app_user() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting('app.user_id', true), '')::uuid
$$;

-- ---------------------------------------------------------------- identity (global, not tenant data)
CREATE TABLE users (
  id uuid PRIMARY KEY,
  email citext NOT NULL UNIQUE,
  email_verified_at timestamptz,
  password_hash text,
  google_sub text UNIQUE,
  totp_secret_enc text,
  totp_enabled_at timestamptz,
  backup_codes_hash text[] NOT NULL DEFAULT '{}',
  locale char(2) NOT NULL DEFAULT 'fr' CHECK (locale IN ('fr','en')),
  display_name text CHECK (length(display_name) <= 120),
  is_platform_admin boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_login_at timestamptz,
  disabled_at timestamptz
);

CREATE TABLE sessions (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash char(64) NOT NULL UNIQUE,
  csrf_token text NOT NULL,
  ip_hash char(64),
  user_agent text,
  mfa_passed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);
CREATE INDEX ix_sessions_user ON sessions(user_id) WHERE revoked_at IS NULL;

-- One-time tokens: email verification, magic link, password reset.
CREATE TABLE email_tokens (
  id uuid PRIMARY KEY,
  user_id uuid REFERENCES users(id) ON DELETE CASCADE,
  email citext NOT NULL,
  purpose text NOT NULL CHECK (purpose IN ('verify_email','magic_link','password_reset')),
  token_hash char(64) NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- organisations
CREATE TABLE organizations (
  id uuid PRIMARY KEY,
  name text NOT NULL CHECK (length(name) BETWEEN 2 AND 120),
  slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  plan_code text NOT NULL DEFAULT 'discovery',
  country char(2) NOT NULL DEFAULT 'CM',
  currency char(3) NOT NULL DEFAULT 'XAF',
  data_region text NOT NULL DEFAULT 'eu-1',
  is_nonprofit boolean NOT NULL DEFAULT false,
  viewer_can_export boolean NOT NULL DEFAULT false,
  data_key_wrapped text NOT NULL,
  referral_code text NOT NULL UNIQUE,
  referred_by uuid,
  verified_at timestamptz,
  suspended_at timestamptz,
  suspended_reason text,
  quota_exceeded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('owner','admin','editor','viewer')),
  notify_each_response boolean NOT NULL DEFAULT true,
  notify_daily_digest boolean NOT NULL DEFAULT false,
  invited_by uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, user_id)
);
CREATE INDEX ix_memberships_user ON memberships(user_id);

CREATE TABLE invitations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  email citext NOT NULL,
  role text NOT NULL CHECK (role IN ('admin','editor','viewer')),
  token_hash char(64) NOT NULL UNIQUE,
  invited_by uuid NOT NULL,
  expires_at timestamptz NOT NULL,
  accepted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE folders (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
  parent_id uuid REFERENCES folders(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- forms
CREATE TABLE forms (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  folder_id uuid REFERENCES folders(id) ON DELETE SET NULL,
  title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  draft_schema jsonb NOT NULL,
  draft_revision integer NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','closed','suspended')),
  short_code text NOT NULL UNIQUE,
  current_version_id uuid,
  closes_at timestamptz,
  max_responses integer CHECK (max_responses > 0),
  retention_days integer CHECK (retention_days > 0),
  allow_embed boolean NOT NULL DEFAULT false,
  publish_block_reason text,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);
CREATE INDEX ix_forms_org_updated ON forms(organization_id, updated_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX ix_forms_title_trgm ON forms USING gin (title gin_trgm_ops);

CREATE TABLE form_versions (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  form_id uuid NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  number integer NOT NULL,
  schema jsonb NOT NULL,
  schema_hash char(64) NOT NULL,
  published_by uuid NOT NULL,
  published_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (form_id, number)
);
ALTER TABLE forms ADD CONSTRAINT fk_forms_current_version FOREIGN KEY (current_version_id)
  REFERENCES form_versions(id) DEFERRABLE INITIALLY DEFERRED;

-- Funnel without tracking cookies (F-ANA-02): daily aggregated counters only.
CREATE TABLE form_funnel (
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  form_id uuid NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  day date NOT NULL,
  step text NOT NULL,
  value bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (form_id, day, step)
);

-- ---------------------------------------------------------------- submissions
CREATE TABLE submissions (
  id uuid PRIMARY KEY,                    -- UUIDv7 created by the browser (rule 5)
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  form_id uuid NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  form_version_id uuid NOT NULL REFERENCES form_versions(id),
  answers jsonb NOT NULL DEFAULT '{}',
  computed jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'new' CHECK (status IN ('new','in_progress','done','rejected')),
  is_partial boolean NOT NULL DEFAULT false,
  last_field_id text,
  payment_status text NOT NULL DEFAULT 'none'
    CHECK (payment_status IN ('none','pending_payment','pending','paid','failed','expired','refunded')),
  amount_due bigint,
  currency char(3),
  locale char(2) NOT NULL DEFAULT 'fr',
  source text CHECK (length(source) <= 64),
  hidden jsonb NOT NULL DEFAULT '{}',
  consent_version text,
  resume_code_hash char(64),
  resume_expires_at timestamptz,
  over_quota boolean NOT NULL DEFAULT false,
  started_at timestamptz NOT NULL DEFAULT now(),
  submitted_at timestamptz,
  anonymized_at timestamptz,
  deleted_at timestamptz
);
CREATE INDEX ix_submissions_form_submitted ON submissions(form_id, submitted_at DESC, id DESC);
CREATE INDEX ix_submissions_org ON submissions(organization_id);
CREATE INDEX ix_submissions_resume ON submissions(resume_code_hash) WHERE resume_code_hash IS NOT NULL;

CREATE TABLE submission_events (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  submission_id uuid NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  actor_id uuid,
  from_status text,
  to_status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE idempotency_keys (
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  key text NOT NULL CHECK (length(key) BETWEEN 8 AND 128),
  scope text NOT NULL,
  request_hash char(64) NOT NULL,
  response jsonb,
  status_code integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, scope, key)
);

-- ---------------------------------------------------------------- payments
CREATE TABLE payment_accounts (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  provider text NOT NULL,
  provider_account_id text,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','verified','suspended')),
  onboarding_url text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, provider)
);

CREATE TABLE payments (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  submission_id uuid REFERENCES submissions(id) ON DELETE SET NULL,
  purpose text NOT NULL DEFAULT 'submission' CHECK (purpose IN ('submission','subscription')),
  provider text NOT NULL,
  provider_ref text,
  channel text,
  amount bigint NOT NULL CHECK (amount > 0),
  currency char(3) NOT NULL,
  platform_fee bigint NOT NULL DEFAULT 0,
  provider_fee bigint NOT NULL DEFAULT 0,
  fee_bearer text NOT NULL DEFAULT 'org' CHECK (fee_bearer IN ('org','payer')),
  status text NOT NULL DEFAULT 'created'
    CHECK (status IN ('created','pending','succeeded','failed','expired','refunded')),
  failure_reason text,
  idempotency_key text NOT NULL UNIQUE,
  payer_msisdn_hash char(64),
  receipt_number text UNIQUE,
  raw_events jsonb NOT NULL DEFAULT '[]',
  expires_at timestamptz NOT NULL,
  next_poll_at timestamptz,
  poll_attempts integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_payments_provider_ref ON payments(provider, provider_ref) WHERE provider_ref IS NOT NULL;
CREATE INDEX ix_payments_org_created ON payments(organization_id, created_at DESC);
CREATE INDEX ix_payments_pending ON payments(next_poll_at) WHERE status IN ('created','pending');
-- At most one successful payment per submission.
CREATE UNIQUE INDEX uq_payments_submission_succeeded ON payments(submission_id) WHERE status = 'succeeded';

CREATE TABLE ticket_categories (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  form_id uuid NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  block_id text NOT NULL,
  option_id text NOT NULL,
  name text NOT NULL,
  quota integer CHECK (quota >= 0),
  price bigint NOT NULL CHECK (price >= 0),
  issued integer NOT NULL DEFAULT 0,
  reserved integer NOT NULL DEFAULT 0,
  UNIQUE (form_id, block_id, option_id)
);

CREATE TABLE tickets (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  form_id uuid NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  submission_id uuid NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  category_id uuid NOT NULL REFERENCES ticket_categories(id),
  serial integer NOT NULL,
  signed_token text NOT NULL,
  token_hash char(64) NOT NULL UNIQUE,
  issued_at timestamptz NOT NULL DEFAULT now(),
  scanned_at timestamptz,
  scanned_by uuid,
  UNIQUE (category_id, serial)
);

CREATE TABLE reconciliation_alerts (
  id uuid PRIMARY KEY,
  organization_id uuid REFERENCES organizations(id) ON DELETE CASCADE,
  provider text NOT NULL,
  provider_ref text,
  payment_id uuid,
  kind text NOT NULL CHECK (kind IN ('amount_mismatch','status_mismatch','unknown_transaction','missing_at_provider')),
  details jsonb NOT NULL DEFAULT '{}',
  resolved_at timestamptz,
  resolved_by uuid,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- billing
CREATE TABLE subscriptions (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  plan_code text NOT NULL,
  billing_period text NOT NULL CHECK (billing_period IN ('monthly','yearly')),
  amount bigint NOT NULL,
  currency char(3) NOT NULL,
  period_start timestamptz,
  period_end timestamptz,
  status text NOT NULL CHECK (status IN ('pending_payment','active','past_due','canceled','expired')),
  pioneer boolean NOT NULL DEFAULT false,
  discount_bps integer NOT NULL DEFAULT 0,
  payment_id uuid REFERENCES payments(id),
  reminded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE SEQUENCE invoice_number_seq;
CREATE TABLE invoices (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  number text NOT NULL UNIQUE,
  kind text NOT NULL DEFAULT 'subscription',
  amount bigint NOT NULL,
  currency char(3) NOT NULL,
  payment_id uuid REFERENCES payments(id),
  lines jsonb NOT NULL DEFAULT '[]',
  issued_at timestamptz NOT NULL DEFAULT now(),
  pdf_key text
);

CREATE TABLE usage_counters (
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  metric text NOT NULL,
  period text NOT NULL,
  value bigint NOT NULL DEFAULT 0,
  alerted_at timestamptz,
  PRIMARY KEY (organization_id, metric, period)
);

-- ---------------------------------------------------------------- integrations and messaging
CREATE TABLE webhook_endpoints (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  form_id uuid REFERENCES forms(id) ON DELETE CASCADE,
  url text NOT NULL CHECK (url ~ '^https://' AND length(url) <= 2048),
  secret_enc text NOT NULL,
  events text[] NOT NULL DEFAULT '{submission.completed}',
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE webhook_deliveries (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  endpoint_id uuid NOT NULL REFERENCES webhook_endpoints(id) ON DELETE CASCADE,
  event text NOT NULL,
  event_id uuid NOT NULL,
  payload jsonb NOT NULL,
  payload_hash char(64) NOT NULL,
  attempt integer NOT NULL DEFAULT 0,
  status_code integer,
  error text,
  next_retry_at timestamptz,
  delivered_at timestamptz,
  failed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_webhook_deliveries_due ON webhook_deliveries(next_retry_at) WHERE delivered_at IS NULL AND failed_at IS NULL;

CREATE TABLE integrations_google_sheets (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  form_id uuid NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  spreadsheet_id text,
  token_enc text,
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE message_logs (
  id uuid PRIMARY KEY,
  organization_id uuid REFERENCES organizations(id) ON DELETE CASCADE,
  channel text NOT NULL CHECK (channel IN ('email','whatsapp','sms')),
  template text NOT NULL,
  to_hash char(64) NOT NULL,
  status text NOT NULL,
  cost_units integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE api_keys (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name text NOT NULL,
  key_hash char(64) NOT NULL UNIQUE,
  prefix text NOT NULL,
  scopes text[] NOT NULL DEFAULT '{}',
  last_used_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- trust and audit
CREATE TABLE audit_events (
  id uuid PRIMARY KEY,
  organization_id uuid REFERENCES organizations(id) ON DELETE CASCADE,
  actor_id uuid,
  action text NOT NULL,
  target_type text,
  target_id text,
  ip_hash char(64),
  metadata jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  previous_hash char(64),
  hash char(64) NOT NULL
);
CREATE INDEX ix_audit_org_created ON audit_events(organization_id, created_at DESC);

CREATE TABLE abuse_reports (
  id uuid PRIMARY KEY,
  form_id uuid NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  reason text NOT NULL CHECK (reason IN ('phishing','scam','inappropriate','other')),
  details text CHECK (length(details) <= 2000),
  reporter_contact_enc text,
  snapshot jsonb NOT NULL,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','dismissed','actioned')),
  decided_by uuid,
  decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE publication_reviews (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  form_id uuid NOT NULL REFERENCES forms(id) ON DELETE CASCADE,
  matches jsonb NOT NULL,
  message text CHECK (length(message) <= 2000),
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','approved','rejected')),
  decided_by uuid,
  decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE verification_requests (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  document_key text NOT NULL,
  document_type text NOT NULL CHECK (document_type IN ('rccm','association_receipt','official_letter')),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  note text,
  decided_by uuid,
  decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE files (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  key text NOT NULL UNIQUE,
  content_type text NOT NULL,
  size_bytes bigint NOT NULL,
  scan_status text NOT NULL DEFAULT 'pending' CHECK (scan_status IN ('pending','clean','infected','skipped')),
  purpose text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- row level security
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['invitations','folders','forms','form_versions','form_funnel','submissions',
    'submission_events','idempotency_keys','payment_accounts','payments','ticket_categories','tickets',
    'subscriptions','invoices','usage_counters','webhook_endpoints','webhook_deliveries',
    'integrations_google_sheets','api_keys','abuse_reports','publication_reviews','verification_requests',
    'files']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY org_isolation ON %I USING (organization_id = app_org()) '
                   'WITH CHECK (organization_id = app_org())', t);
  END LOOP;
END $$;

-- Tables with a nullable organization_id: a row with NULL is a platform row, never visible to tenants.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['audit_events','message_logs','reconciliation_alerts']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY org_isolation ON %I USING (organization_id = app_org()) '
                   'WITH CHECK (organization_id = app_org())', t);
  END LOOP;
END $$;

ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY membership_visibility ON memberships
  USING (organization_id = app_org() OR user_id = app_user())
  WITH CHECK (organization_id = app_org());

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY org_self ON organizations
  USING (id = app_org() OR id IN (SELECT organization_id FROM memberships WHERE user_id = app_user()))
  WITH CHECK (id = app_org());

-- Narrow resolver used by public routes and provider webhooks to find the tenant of a public key.
-- SECURITY DEFINER: runs as arha_owner, returns only an organisation id, never row data.
CREATE OR REPLACE FUNCTION resolve_org(kind text, key text) RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $$
DECLARE result uuid;
BEGIN
  IF kind = 'form_code' THEN
    SELECT organization_id INTO result FROM forms WHERE short_code = key AND deleted_at IS NULL;
  ELSIF kind = 'payment_id' THEN
    SELECT organization_id INTO result FROM payments WHERE id = key::uuid;
  ELSIF kind = 'payment_ref' THEN
    SELECT organization_id INTO result FROM payments WHERE provider_ref = key;
  ELSIF kind = 'payment_reference' THEN
    SELECT organization_id INTO result FROM payments WHERE id::text = key OR idempotency_key = key;
  ELSIF kind = 'invitation' THEN
    SELECT organization_id INTO result FROM invitations WHERE token_hash = key;
  ELSIF kind = 'ticket' THEN
    SELECT organization_id INTO result FROM tickets WHERE token_hash = key;
  ELSIF kind = 'resume' THEN
    SELECT organization_id INTO result FROM submissions WHERE resume_code_hash = key;
  ELSE
    RAISE EXCEPTION 'unknown resolver kind %', kind;
  END IF;
  RETURN result;
EXCEPTION WHEN invalid_text_representation THEN
  RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION resolve_org(text, text) FROM PUBLIC;

-- ---------------------------------------------------------------- grants
GRANT USAGE ON SCHEMA public TO arha_app, arha_platform;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO arha_app, arha_platform;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO arha_app, arha_platform;
GRANT EXECUTE ON FUNCTION resolve_org(text, text) TO arha_app, arha_platform;
GRANT EXECUTE ON FUNCTION app_org(), app_user() TO arha_app, arha_platform;
-- The audit log is append only for the application.
REVOKE UPDATE, DELETE ON audit_events FROM arha_app;

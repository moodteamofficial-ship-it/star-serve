-- Star Serve — Auth / RBAC schema (reference SQL) — idempotent
-- Source of truth: Alembic migrations under backend/alembic/versions/
--   0001_phase1_foundation.py   — create tenants, branches, users, roles, sessions, …
--   0008_secure_users_roles_rls.py — role_id, FORCE RLS, column guards
--   0009_soft_delete_auth.py    — deleted_at / deleted_by / status soft-delete
--   0010_user_profile_columns.py — otp, geo, country, currency, branch, gender
--   0011_reference_countries_currencies.py — currencies, countries + FKs
--
-- HARD DELETE IS FORBIDDEN. Soft-delete only:
--   status = 'DELETED', deleted_at = now(), deleted_by = <actor user id>
-- OTP is stored as otp_hash only — never returned by the API.
--
-- Safe to re-run: CREATE IF NOT EXISTS + ON CONFLICT DO NOTHING.
-- IDs: UUID PRIMARY KEY DEFAULT gen_random_uuid() (Postgres 13+ / Supabase).
--
-- Create order (FK deps):
--   tenants → currencies → countries → branches → roles → users
--     → sessions → user_roles
-- Every tenant_id REFERENCES tenants(id).

-- ---------------------------------------------------------------------------
-- tenants (must exist before users / roles / branches / sessions / user_roles)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_name VARCHAR(255) NOT NULL,
  trading_name VARCHAR(255) NOT NULL,
  tenant_type VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  registration_number VARCHAR(128),
  kra_pin VARCHAR(32),
  email VARCHAR(255),
  phone VARCHAR(64),
  subscription_plan VARCHAR(64),
  database_mode VARCHAR(32) NOT NULL,
  dedicated_database_dsn TEXT,
  configuration JSONB NOT NULL DEFAULT '{}',
  branding JSONB NOT NULL DEFAULT '{}',
  is_platform BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE tenants ALTER COLUMN id SET DEFAULT gen_random_uuid();

-- ISO 4217 currency catalog (users.currency, countries.currency_code)
CREATE TABLE IF NOT EXISTS currencies (
  code VARCHAR(8) PRIMARY KEY,           -- e.g. KES, USD
  name VARCHAR(128) NOT NULL,
  symbol VARCHAR(16),                    -- e.g. KSh, $
  decimal_places INTEGER NOT NULL DEFAULT 2,
  status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  deleted_at TIMESTAMPTZ,
  deleted_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Country catalog (users.country_id / country_code / phone_country_code)
CREATE TABLE IF NOT EXISTS countries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  iso2 VARCHAR(2) NOT NULL UNIQUE,       -- e.g. KE
  iso3 VARCHAR(3),                       -- e.g. KEN
  name VARCHAR(128) NOT NULL,
  phone_code VARCHAR(8),                 -- e.g. +254
  currency_code VARCHAR(8) REFERENCES currencies(code) ON DELETE SET NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  deleted_at TIMESTAMPTZ,
  deleted_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed core currencies / countries (skip if already present)
INSERT INTO currencies (code, name, symbol, decimal_places, status) VALUES
  ('KES', 'Kenyan Shilling', 'KSh', 2, 'ACTIVE'),
  ('UGX', 'Ugandan Shilling', 'USh', 0, 'ACTIVE'),
  ('TZS', 'Tanzanian Shilling', 'TSh', 2, 'ACTIVE'),
  ('USD', 'US Dollar', '$', 2, 'ACTIVE'),
  ('GBP', 'British Pound', '£', 2, 'ACTIVE'),
  ('EUR', 'Euro', '€', 2, 'ACTIVE')
ON CONFLICT (code) DO NOTHING;

INSERT INTO countries (id, iso2, iso3, name, phone_code, currency_code, status) VALUES
  (gen_random_uuid(), 'KE', 'KEN', 'Kenya', '+254', 'KES', 'ACTIVE'),
  (gen_random_uuid(), 'UG', 'UGA', 'Uganda', '+256', 'UGX', 'ACTIVE'),
  (gen_random_uuid(), 'TZ', 'TZA', 'Tanzania', '+255', 'TZS', 'ACTIVE'),
  (gen_random_uuid(), 'US', 'USA', 'United States', '+1', 'USD', 'ACTIVE'),
  (gen_random_uuid(), 'GB', 'GBR', 'United Kingdom', '+44', 'GBP', 'ACTIVE')
ON CONFLICT (iso2) DO NOTHING;

-- Referenced by users.branch_id / user_roles.branch_id
CREATE TABLE IF NOT EXISTS branches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
  name VARCHAR(255) NOT NULL,
  code VARCHAR(64),
  status VARCHAR(32) NOT NULL,
  country_id UUID REFERENCES countries(id) ON DELETE SET NULL,
  country_code VARCHAR(8),               -- denormalized iso2 e.g. KE
  phone VARCHAR(64),
  email VARCHAR(255),
  address_line VARCHAR(512),
  city VARCHAR(128),
  lat NUMERIC(10, 7),
  lng NUMERIC(10, 7),
  deleted_at TIMESTAMPTZ,
  deleted_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Created before users so users.role_id can reference it.
CREATE TABLE IF NOT EXISTS roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE RESTRICT,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  description TEXT,
  is_system BOOLEAN NOT NULL DEFAULT false,
  status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  deleted_at TIMESTAMPTZ,
  deleted_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
  role_id UUID REFERENCES roles(id) ON DELETE RESTRICT,
  branch_id UUID REFERENCES branches(id) ON DELETE SET NULL,
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(64),
  phone_country_code VARCHAR(8),       -- e.g. +254 (from countries.phone_code)
  country_code VARCHAR(8),             -- ISO alpha-2 e.g. KE (from countries.iso2)
  country_id UUID REFERENCES countries(id) ON DELETE SET NULL,
  currency VARCHAR(8) NOT NULL DEFAULT 'KES' REFERENCES currencies(code) ON DELETE RESTRICT,
  gender VARCHAR(32),                  -- MALE | FEMALE | OTHER | PREFER_NOT_TO_SAY
  lat NUMERIC(10, 7),
  lng NUMERIC(10, 7),
  timezone VARCHAR(64),
  locale VARCHAR(16),
  avatar_url VARCHAR(512),
  full_name VARCHAR(255) NOT NULL,
  password_hash TEXT NOT NULL,
  otp_hash VARCHAR(128),               -- hashed OTP; never expose
  otp_expires_at TIMESTAMPTZ,
  otp_attempts INTEGER NOT NULL DEFAULT 0,
  otp_channel VARCHAR(16),             -- sms | email | whatsapp
  status VARCHAR(32) NOT NULL,         -- ACTIVE | PENDING | LOCKED | DISABLED | DELETED
  email_verified_at TIMESTAMPTZ,
  is_platform_admin BOOLEAN NOT NULL DEFAULT false,
  failed_login_attempts INTEGER NOT NULL DEFAULT 0,
  locked_until TIMESTAMPTZ,
  last_login_at TIMESTAMPTZ,
  mfa_enabled BOOLEAN NOT NULL DEFAULT false,
  preferred_app_env VARCHAR(32) NOT NULL DEFAULT 'development',
  deleted_at TIMESTAMPTZ,
  deleted_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  role_id UUID REFERENCES roles(id) ON DELETE RESTRICT,
  app_env VARCHAR(32),
  status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  refresh_token_hash VARCHAR(128) NOT NULL UNIQUE,
  family_id UUID NOT NULL DEFAULT gen_random_uuid(),
  user_agent VARCHAR(512),
  ip_address VARCHAR(64),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  reused_at TIMESTAMPTZ,
  device_label VARCHAR(128),
  meta JSONB NOT NULL DEFAULT '{}',
  deleted_at TIMESTAMPTZ,
  deleted_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  role_id UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
  branch_id UUID REFERENCES branches(id) ON DELETE SET NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  deleted_at TIMESTAMPTZ,
  deleted_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ensure UUID defaults exist even if tables were created earlier without them
ALTER TABLE countries ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE branches ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE roles ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE users ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE sessions ALTER COLUMN id SET DEFAULT gen_random_uuid();
ALTER TABLE sessions ALTER COLUMN family_id SET DEFAULT gen_random_uuid();
ALTER TABLE user_roles ALTER COLUMN id SET DEFAULT gen_random_uuid();

-- Add tenant FKs if tables pre-existed without them (CREATE IF NOT EXISTS cannot alter)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_branches_tenant_id') THEN
    ALTER TABLE branches
      ADD CONSTRAINT fk_branches_tenant_id
      FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_roles_tenant_id') THEN
    ALTER TABLE roles
      ADD CONSTRAINT fk_roles_tenant_id
      FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_tenant_id') THEN
    ALTER TABLE users
      ADD CONSTRAINT fk_users_tenant_id
      FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_sessions_tenant_id') THEN
    ALTER TABLE sessions
      ADD CONSTRAINT fk_sessions_tenant_id
      FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_roles_tenant_id') THEN
    ALTER TABLE user_roles
      ADD CONSTRAINT fk_user_roles_tenant_id
      FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_roles_deleted_by_users') THEN
    ALTER TABLE roles
      ADD CONSTRAINT fk_roles_deleted_by_users
      FOREIGN KEY (deleted_by) REFERENCES users(id) ON DELETE SET NULL;
  END IF;
END $$;

-- Platform tenant (login requires a matching tenants row)
INSERT INTO tenants (
  id, legal_name, trading_name, tenant_type, status, database_mode, is_platform, email
)
SELECT
  gen_random_uuid(),
  'Star Serve Platform',
  'Star Serve',
  'PLATFORM',
  'ACTIVE',
  'SHARED_DATABASE',
  true,
  'platform@starserve.local'
WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE is_platform = true);

-- ---------------------------------------------------------------------------
-- Seed: Super Admin role + Lawrence Larry
-- tenant_id is always the real platform tenants.id (never a free-floating UUID).
-- Login: lawrence.larry@starserve.local / 11111111
-- Skips if email already exists.
-- ---------------------------------------------------------------------------

WITH platform AS (
  SELECT id AS tenant_id
  FROM tenants
  WHERE is_platform = true
  LIMIT 1
),
should_seed AS (
  SELECT p.tenant_id
  FROM platform p
  WHERE NOT EXISTS (
    SELECT 1 FROM users
    WHERE email = 'lawrence.larry@starserve.local' AND deleted_at IS NULL
  )
),
kenya AS (
  SELECT id, iso2, phone_code, currency_code
  FROM countries
  WHERE iso2 = 'KE'
  LIMIT 1
),
new_role AS (
  INSERT INTO roles (id, tenant_id, code, name, description, is_system, status)
  SELECT
    gen_random_uuid(),
    s.tenant_id,
    'platform_admin',
    'Super Administrator',
    'Full platform super admin — all tenants and system settings',
    true,
    'ACTIVE'
  FROM should_seed s
  WHERE NOT EXISTS (
    SELECT 1 FROM roles r
    WHERE r.tenant_id = s.tenant_id AND r.code = 'platform_admin' AND r.deleted_at IS NULL
  )
  RETURNING id, tenant_id
),
role_row AS (
  SELECT id, tenant_id FROM new_role
  UNION ALL
  SELECT r.id, r.tenant_id
  FROM roles r
  JOIN should_seed s ON s.tenant_id = r.tenant_id
  WHERE r.code = 'platform_admin' AND r.deleted_at IS NULL
    AND NOT EXISTS (SELECT 1 FROM new_role)
  LIMIT 1
),
new_user AS (
  INSERT INTO users (
    id,
    tenant_id,
    role_id,
    email,
    full_name,
    password_hash,
    status,
    is_platform_admin,
    country_id,
    country_code,
    phone_country_code,
    currency,
    email_verified_at
  )
  SELECT
    gen_random_uuid(),
    r.tenant_id,   -- = tenants.id of platform tenant
    r.id,
    'lawrence.larry@starserve.local',
    'Lawrence Larry',
    '$argon2id$v=19$m=65536,t=3,p=4$Pmo4Ji8CGTrgaK1piGLK3A$UC6nX5KLfksGsfRb/RhBR1PSzbD2HPepkJXklmwuyAE',
    'ACTIVE',
    true,
    k.id,
    k.iso2,
    k.phone_code,
    COALESCE(k.currency_code, 'KES'),
    now()
  FROM role_row r
  CROSS JOIN kenya k
  RETURNING id, tenant_id, role_id
)
INSERT INTO user_roles (id, tenant_id, user_id, role_id, status)
SELECT gen_random_uuid(), u.tenant_id, u.id, u.role_id, 'ACTIVE'
FROM new_user u;

"""Sync ops commission settings, backfill policy agents, accrue missed ledger rows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0036_ops_visibility_commissions"
down_revision: Union[str, None] = "0035_rehome_platform_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Push platform commission plan onto the guest/ops agency (where payments settle).
    conn.execute(
        sa.text(
            """
            WITH agency AS (
              SELECT id
              FROM tenants
              WHERE COALESCE(is_platform, false) = false
                AND status = 'ACTIVE'
              ORDER BY created_at ASC, id ASC
              LIMIT 1
            ),
            platform AS (
              SELECT id
              FROM tenants
              WHERE COALESCE(is_platform, false) = true
              ORDER BY created_at ASC, id ASC
              LIMIT 1
            ),
            src AS (
              SELECT s.*
              FROM commission_settings s
              JOIN platform p ON p.id = s.tenant_id
            )
            INSERT INTO commission_settings (
              id, tenant_id, updated_by_user_id, currency, payout_cadence,
              certificate_rate_percent, claim_rate_percent, enabled, notes, version,
              created_at, updated_at
            )
            SELECT
              :new_id,
              (SELECT id FROM agency),
              src.updated_by_user_id,
              src.currency,
              src.payout_cadence,
              src.certificate_rate_percent,
              src.claim_rate_percent,
              src.enabled,
              src.notes,
              COALESCE(src.version, 1),
              NOW(),
              NOW()
            FROM src
            WHERE EXISTS (SELECT 1 FROM agency)
              AND NOT EXISTS (
                SELECT 1 FROM commission_settings cs
                WHERE cs.tenant_id = (SELECT id FROM agency)
              )
            """
        ),
        {"new_id": str(uuid4())},
    )
    conn.execute(
        sa.text(
            """
            WITH agency AS (
              SELECT id
              FROM tenants
              WHERE COALESCE(is_platform, false) = false
                AND status = 'ACTIVE'
              ORDER BY created_at ASC, id ASC
              LIMIT 1
            ),
            platform AS (
              SELECT id
              FROM tenants
              WHERE COALESCE(is_platform, false) = true
              ORDER BY created_at ASC, id ASC
              LIMIT 1
            ),
            src AS (
              SELECT s.*
              FROM commission_settings s
              JOIN platform p ON p.id = s.tenant_id
            )
            UPDATE commission_settings dst
            SET
              currency = src.currency,
              payout_cadence = src.payout_cadence,
              certificate_rate_percent = src.certificate_rate_percent,
              claim_rate_percent = src.claim_rate_percent,
              enabled = src.enabled,
              notes = src.notes,
              version = GREATEST(COALESCE(dst.version, 1), COALESCE(src.version, 1)),
              updated_at = NOW()
            FROM src, agency
            WHERE dst.tenant_id = agency.id
            """
        )
    )

    # 2) Copy proposal intermediary onto policies that lost the FK.
    conn.execute(
        sa.text(
            """
            UPDATE policies p
            SET intermediary_id = pr.intermediary_id
            FROM proposals pr
            WHERE p.proposal_id = pr.id
              AND p.intermediary_id IS NULL
              AND pr.intermediary_id IS NOT NULL
            """
        )
    )

    # 3) Accrue missing ledger lines for SUCCESS payments (agent or house).
    settings = (
        conn.execute(
            sa.text(
                """
                SELECT cs.tenant_id, cs.certificate_rate_percent, cs.enabled, cs.currency, cs.version
                FROM commission_settings cs
                JOIN tenants t ON t.id = cs.tenant_id
                WHERE COALESCE(t.is_platform, false) = false
                  AND t.status = 'ACTIVE'
                ORDER BY t.created_at ASC
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )
    if not settings or not settings["enabled"]:
        return

    rate = Decimal(str(settings["certificate_rate_percent"] or 0))
    if rate <= 0:
        return

    tenant_id = settings["tenant_id"]
    currency = settings["currency"] or "KES"
    settings_version = int(settings["version"] or 1)

    payments = (
        conn.execute(
            sa.text(
                """
                SELECT
                  pay.id AS payment_id,
                  pay.amount,
                  pay.currency,
                  pay.reference,
                  pay.paid_at,
                  pay.branch_id,
                  pay.created_at,
                  p.id AS policy_id,
                  p.policy_number,
                  p.vehicle_registration,
                  p.proposal_id,
                  p.intermediary_id,
                  p.intermediary_name,
                  i.agent_code,
                  i.name AS agent_name,
                  i.status AS agent_status
                FROM payments pay
                JOIN policies p ON p.id = pay.policy_id
                LEFT JOIN intermediaries i ON i.id = p.intermediary_id AND i.deleted_at IS NULL
                WHERE pay.tenant_id = :tenant_id
                  AND pay.status = 'SUCCESS'
                  AND NOT EXISTS (
                    SELECT 1 FROM commission_ledger_entries e
                    WHERE e.tenant_id = pay.tenant_id
                      AND e.payment_id = pay.id
                      AND e.entry_kind IN ('ACCRUAL', 'HOUSE')
                  )
                ORDER BY COALESCE(pay.paid_at, pay.created_at) ASC, pay.created_at ASC
                """
            ),
            {"tenant_id": tenant_id},
        )
        .mappings()
        .all()
    )

    balances: dict[str | None, Decimal] = {}
    now = datetime.now(UTC)
    for row in payments:
        base = Decimal(str(row["amount"] or 0))
        if base <= 0:
            continue
        commission = _money(base * rate / Decimal("100"))
        if commission <= 0:
            continue

        agent_ok = (
            row["intermediary_id"] is not None
            and str(row["agent_status"] or "").upper() == "APPROVED"
        )
        intermediary_id = row["intermediary_id"] if agent_ok else None
        entry_kind = "ACCRUAL" if agent_ok else "HOUSE"
        account_key = str(intermediary_id) if intermediary_id else None
        prev = balances.get(account_key, Decimal("0.00"))
        balance_after = _money(prev + commission)
        balances[account_key] = balance_after

        agent_code = row["agent_code"] if agent_ok else None
        agent_name = (row["agent_name"] or row["intermediary_name"]) if agent_ok else "Star Serve"
        description = (
            f"Commission on paid certificate {row['policy_number']}"
            if agent_ok
            else f"House retention on paid certificate {row['policy_number']}"
        )
        occurred = row["paid_at"] or row["created_at"] or now
        metadata = {
            "payment_reference": row["reference"],
            "policy_number": row["policy_number"],
            "vehicle_registration": row["vehicle_registration"],
            "beneficiary": "AGENT" if agent_ok else "HOUSE",
            "backfill": True,
        }

        conn.execute(
            sa.text(
                """
                INSERT INTO commission_ledger_entries (
                  id, tenant_id, branch_id, intermediary_id, created_by_user_id,
                  statement_ref, entry_kind, direction, source_event,
                  amount, balance_after, currency,
                  agent_code_snapshot, intermediary_name_snapshot,
                  base_amount, rate_percent_snapshot, settings_version,
                  payment_id, policy_id, proposal_id, certificate_id, claim_id, payout_batch_id,
                  description, occurred_at, metadata, created_at, updated_at
                ) VALUES (
                  :id, :tenant_id, :branch_id, :intermediary_id, NULL,
                  :statement_ref, :entry_kind, 'CREDIT', 'CERTIFICATE_PAYMENT',
                  :amount, :balance_after, :currency,
                  :agent_code, :agent_name,
                  :base_amount, :rate, :settings_version,
                  :payment_id, :policy_id, :proposal_id, NULL, NULL, NULL,
                  :description, :occurred_at,
                  CAST(:metadata AS jsonb), :now, :now
                )
                ON CONFLICT ON CONSTRAINT uq_commission_ledger_payment_kind DO NOTHING
                """
            ),
            {
                "id": str(uuid4()),
                "tenant_id": tenant_id,
                "branch_id": row["branch_id"],
                "intermediary_id": intermediary_id,
                "statement_ref": f"CML-{uuid4().hex[:10].upper()}",
                "entry_kind": entry_kind,
                "amount": str(commission),
                "balance_after": str(balance_after),
                "currency": row["currency"] or currency,
                "agent_code": agent_code,
                "agent_name": agent_name,
                "base_amount": str(_money(base)),
                "rate": str(rate),
                "settings_version": settings_version,
                "payment_id": row["payment_id"],
                "policy_id": row["policy_id"],
                "proposal_id": row["proposal_id"],
                "description": description[:500],
                "occurred_at": occurred,
                "metadata": json.dumps(metadata),
                "now": now,
            },
        )


def downgrade() -> None:
    # Data backfill is not reversed.
    pass

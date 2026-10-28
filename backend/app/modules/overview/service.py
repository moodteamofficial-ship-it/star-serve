"""Tenant overview aggregates — permission-gated, low RTT, short-lived cache.

High-latency Postgres (Supabase pooler) dominates cost: ~1 RTT ≈ 300–500ms.
Strategy:
1. Reuse the request session (RLS already bound) — never open extra sessions.
2. Collapse each domain into one SQL statement (FILTER / date_trunc / jsonb).
3. Cache the assembled payload briefly (Redis, with in-process fallback).
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from calendar import month_abbr
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.redis_client import get_redis_client
from app.core.security.branch_scope import BranchScope
from app.core.security.context import SecurityContext

WEEKDAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
_CACHE_TTL_S = 20
_CACHE_PREFIX = "overview:v9"

# Process-local fallback when Redis is down (still tenant+user keyed).
_mem_lock = threading.Lock()
_mem_cache: dict[str, tuple[float, str]] = {}


def _can(ctx: SecurityContext, *codes: str) -> bool:
    return ctx.allows(*codes)


def _period_bounds(key: str, *, now: datetime | None = None) -> tuple[datetime, datetime, datetime, datetime]:
    end = now or datetime.now(UTC)
    if key == "ytd":
        start = datetime(end.year, 1, 1, tzinfo=UTC)
        compare_end = start - timedelta(microseconds=1)
        compare_start = datetime(end.year - 1, 1, 1, tzinfo=UTC)
        return start, end, compare_start, compare_end

    days = {"7d": 7, "30d": 30, "90d": 90}.get(key, 30)
    start = end - timedelta(days=days)
    compare_end = start
    compare_start = compare_end - timedelta(days=days)
    return start, end, compare_start, compare_end


def _money(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _month_keys(end: datetime, months_back: int = 5) -> tuple[datetime, list[tuple[int, int]]]:
    keys: list[tuple[int, int]] = []
    for i in range(months_back, -1, -1):
        year = end.year
        month = end.month - i
        while month <= 0:
            month += 12
            year -= 1
        keys.append((year, month))
    y0, m0 = keys[0]
    return datetime(y0, m0, 1, tzinfo=UTC), keys


def _peak_weekday_from_map(raw: dict[str, Any] | None) -> str | None:
    if not raw:
        return None
    counts = [0] * 7
    for k, v in raw.items():
        try:
            idx = int(float(k))
        except (TypeError, ValueError):
            continue
        if 0 <= idx <= 6:
            counts[idx] += int(v or 0)
    if not any(counts):
        return None
    return WEEKDAYS[max(range(7), key=lambda i: counts[i])]


def _week_from_map(end: datetime, raw: dict[str, Any] | None) -> list[int]:
    bucket_start = (end - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    by_day: dict[str, int] = {}
    if raw:
        for k, v in raw.items():
            by_day[str(k)[:10]] = int(v or 0)
    out: list[int] = []
    for i in range(7):
        day = (bucket_start + timedelta(days=i)).date().isoformat()
        out.append(by_day.get(day, 0))
    return out


def _fill_months_count(keys: list[tuple[int, int]], raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    by_key: dict[str, int] = {}
    if raw:
        for k, v in raw.items():
            by_key[str(k)[:7]] = int(v or 0)
    return [
        {"key": f"{y}-{m:02d}", "label": month_abbr[m], "count": by_key.get(f"{y}-{m:02d}", 0)}
        for y, m in keys
    ]


def _fill_months_amount(keys: list[tuple[int, int]], raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    by_key: dict[str, float] = {}
    if raw:
        for k, v in raw.items():
            by_key[str(k)[:7]] = _money(v)
    return [
        {"key": f"{y}-{m:02d}", "label": month_abbr[m], "amount": by_key.get(f"{y}-{m:02d}", 0.0)}
        for y, m in keys
    ]


def _cap_fingerprint(caps: dict[str, bool]) -> str:
    bits = "".join("1" if caps[k] else "0" for k in sorted(caps))
    return hashlib.sha256(bits.encode()).hexdigest()[:16]


def _cache_key(ctx: SecurityContext, period: str, caps: dict[str, bool]) -> str:
    bids = ",".join(sorted(str(b) for b in ctx.branch_ids))
    return (
        f"{_CACHE_PREFIX}:{ctx.tenant_id}:{ctx.user_id}:{ctx.branch_scope}:"
        f"{int(ctx.is_platform_admin)}:{bids}:{period}:{_cap_fingerprint(caps)}"
    )


def _overview_branch_mode(ctx: SecurityContext) -> BranchScope:
    """Pick the compiled overview predicate. Never infer ALL_TENANT from empty ids."""
    if ctx.is_guest or ctx.is_platform_admin or ctx.branch_scope == BranchScope.ALL_TENANT:
        return BranchScope.ALL_TENANT
    if ctx.branch_scope == BranchScope.ASSIGNED and ctx.branch_ids:
        return BranchScope.ASSIGNED
    return BranchScope.NONE


def _mem_get(key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _mem_lock:
        row = _mem_cache.get(key)
        if not row:
            return None
        expires, raw = row
        if expires < now:
            _mem_cache.pop(key, None)
            return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _mem_set(key: str, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, default=str)
    with _mem_lock:
        # Bound memory: drop expired first, then cap size.
        now = time.monotonic()
        expired = [k for k, (exp, _) in _mem_cache.items() if exp < now]
        for k in expired:
            _mem_cache.pop(k, None)
        if len(_mem_cache) > 512:
            _mem_cache.clear()
        _mem_cache[key] = (now + _CACHE_TTL_S, raw)


async def _cache_get(key: str) -> dict[str, Any] | None:
    redis = get_redis_client()
    if redis is not None:
        try:
            raw = await redis.get(key)
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode()
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return _mem_get(key)


async def _cache_set(key: str, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, default=str)
    redis = get_redis_client()
    if redis is not None:
        try:
            await redis.set(key, raw, ex=_CACHE_TTL_S)
        except Exception:
            pass
    _mem_set(key, payload)


class OverviewService:
    def __init__(self, session: AsyncSession, ctx: SecurityContext) -> None:
        self.session = session
        self.ctx = ctx

    async def summary(self, *, period: str = "30d") -> dict[str, Any]:
        key = period if period in {"7d", "30d", "90d", "ytd"} else "30d"
        start, end, compare_start, compare_end = _period_bounds(key)

        can_payments = _can(self.ctx, "payment:read")
        can_wallet = _can(self.ctx, "wallet:read")
        can_policies = _can(self.ctx, "policy:read")
        can_customers = _can(self.ctx, "customer:read")
        can_customer_create = _can(self.ctx, "customer:create")
        can_proposals = _can(self.ctx, "proposal:read")
        can_quote = _can(self.ctx, "proposal:create")
        can_certificates = _can(self.ctx, "certificate:read")
        can_agents = _can(self.ctx, "agent:read")
        can_products = _can(self.ctx, "product:read")
        can_audit = _can(self.ctx, "audit:read")
        can_claims = _can(self.ctx, "claim:read")
        can_claim_create = _can(self.ctx, "claim:create")

        caps = {
            "payments": can_payments,
            "wallet": can_wallet,
            "policies": can_policies,
            "customers": can_customers,
            "customer_create": can_customer_create,
            "proposals": can_proposals,
            "quote": can_quote,
            "certificates": can_certificates,
            "agents": can_agents,
            "products": can_products,
            "audit": can_audit,
            "claims": can_claims,
            "claim_create": can_claim_create,
        }

        cache_key = _cache_key(self.ctx, key, caps)
        cached = await _cache_get(cache_key)
        if cached is not None:
            cached = dict(cached)
            cached["cache"] = {"hit": True, "ttl_s": _CACHE_TTL_S}
            return cached

        window_start, month_keys = _month_keys(end, 5)
        week_start = (end - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        days = max(1, min(30, int((end - start).total_seconds() // 86400) + 1))
        daily_start = end - timedelta(days=days - 1)
        today = date.today()
        soon = today + timedelta(days=30)

        # One round-trip: permission-gated JSON blob via RLS-bound session.
        branch_mode = _overview_branch_mode(self.ctx)
        params: dict[str, Any] = {
            "want_payments": can_payments,
            "want_wallet": can_wallet,
            "want_policies": can_policies,
            "want_customers": can_customers,
            "want_proposals": can_proposals,
            "want_certificates": can_certificates,
            "want_agents": can_agents,
            "want_products": can_products,
            "want_audit": can_audit,
            "want_claims": can_claims,
            "want_activity": can_payments
            or can_policies
            or can_customers
            or can_proposals
            or can_claims,
            "tenant_id": str(self.ctx.tenant_id),
            "start": start,
            "end": end,
            "compare_start": compare_start,
            "compare_end": compare_end,
            "window_start": window_start,
            "week_start": week_start,
            "daily_start": daily_start,
            "today": today,
            "soon": soon,
            "followup_soon": end + timedelta(days=7),
        }
        if branch_mode == BranchScope.ASSIGNED:
            params["branch_ids"] = sorted(self.ctx.branch_ids)
        agent_mode = self.ctx.is_sales_agent and self.ctx.agent_intermediary_id is not None
        if self.ctx.is_sales_agent and not agent_mode:
            branch_mode = BranchScope.NONE
        if agent_mode:
            params["agent_id"] = str(self.ctx.agent_intermediary_id)
            params["user_id"] = str(self.ctx.user_id)
        row = (
            await self.session.execute(
                _overview_statement(
                    branch_mode,
                    platform_wide=self.ctx.is_platform_admin,
                    agent=agent_mode,
                ),
                params,
            )
        ).mappings().one()

        blob = row["payload"]
        if isinstance(blob, str):
            blob = json.loads(blob)
        if not isinstance(blob, dict):
            blob = {}

        sections: list[str] = []
        headline: dict[str, Any] = {}
        payload: dict[str, Any] = {
            "period": {
                "key": key,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "compare_start": compare_start.isoformat(),
                "compare_end": compare_end.isoformat(),
            },
            "capabilities": caps,
            "payments": None,
            "premium": None,
            "policies": None,
            "customers": None,
            "proposals": None,
            "certificates": None,
            "agents": None,
            "products": None,
            "wallet": None,
            "activity": None,
            "recent_activity": None,
            "recent_applications": None,
            "premium_growth": None,
            "claims": None,
            "followups": None,
            "quick_actions": None,
        }

        if can_payments and blob.get("payments"):
            payments = _shape_payments_full(
                blob["payments"],
                blob.get("payments_prior"),
                blob.get("payments_daily"),
                days=days,
                daily_start=daily_start,
            )
            sections.append("payments")
            payload["payments"] = payments
            headline["payments_success"] = payments["successful"]
            headline["payments_pending"] = payments["pending"]
            headline["success_rate"] = payments["success_rate"]

            premium = _shape_premium(blob.get("premium") or {}, payments)
            wallet = None
            if can_wallet:
                wallet = _shape_wallet(blob.get("wallet"))
                payload["wallet"] = wallet
                premium["wallet_balance"] = wallet["available_balance"]
                premium["currency"] = wallet["currency"] or premium["currency"]
            if can_wallet or premium["gross"] > 0 or payments["successful"] > 0:
                sections.append("premium")
                payload["premium"] = premium
                headline["gross_premium"] = premium["gross"]
                headline["currency"] = premium["currency"]

            growth = _shape_growth(blob.get("premium_growth") or {}, month_keys)
            sections.append("premium_growth")
            payload["premium_growth"] = growth
            if payload.get("premium") is not None:
                payload["premium"]["growth"] = growth["months"]

        elif can_wallet:
            sections.append("wallet")
            wallet = _shape_wallet(blob.get("wallet"))
            payload["wallet"] = wallet
            headline["wallet_balance"] = wallet["available_balance"]
            headline["currency"] = wallet["currency"]

        if can_policies and blob.get("policies"):
            policies = _shape_policies(blob["policies"], end=end)
            sections.append("policies")
            payload["policies"] = policies
            headline["policies_active"] = policies["active"]
            headline["policies_total"] = policies["total"]
            headline["in_force_premium"] = policies["in_force_premium"]
            headline["expiring_30d"] = policies["expiring_30d"]
            if "currency" not in headline:
                headline["currency"] = policies["currency"]

        if can_customers and blob.get("customers"):
            customers = _shape_customers(blob["customers"], end=end)
            sections.append("customers")
            payload["customers"] = customers
            headline["customers_total"] = customers["total"]
            headline["customers_new"] = customers["created_in_period"]

        if can_proposals and blob.get("proposals"):
            proposals = _shape_proposals(blob["proposals"])
            sections.append("proposals")
            payload["proposals"] = proposals
            headline["proposals_pipeline"] = proposals["in_pipeline"]
            headline["issuance_pct"] = proposals["issuance_pct"]
            headline["pipeline_premium"] = proposals["pipeline_premium"]
            recent_apps = _shape_recent_applications(blob.get("recent_applications") or [])
            payload["recent_applications"] = recent_apps
            if recent_apps:
                sections.append("recent_applications")

        if can_certificates and blob.get("certificates"):
            certificates = _shape_certificates(blob["certificates"])
            sections.append("certificates")
            payload["certificates"] = certificates
            headline["certificates_pending"] = certificates["pending"]

        if can_agents and blob.get("agents"):
            agents = _shape_agents(blob["agents"])
            sections.append("agents")
            payload["agents"] = agents
            headline["agents_approved"] = agents["approved"]

        if can_products and blob.get("products"):
            products = _shape_products(blob["products"])
            sections.append("products")
            payload["products"] = products
            headline["products_active"] = products["active"]

        if can_claims:
            claims = _shape_claims(blob.get("claims") or {}, end=end)
            followups = _shape_followups(blob.get("followups") or {})
            sections.append("claims")
            sections.append("followups")
            payload["claims"] = claims
            payload["followups"] = followups
            headline["claims_open"] = claims["open"]
            headline["claims_intake"] = claims["intake"]
            headline["followups_open"] = followups["open"]
            headline["followups_overdue"] = followups["overdue"]
            if "currency" not in headline:
                headline["currency"] = claims["currency"]

        if (
            can_payments or can_policies or can_customers or can_proposals or can_claims
        ) and blob.get("activity") is not None:
            activity = _shape_activity(blob.get("activity") or {}, month_keys)
            sections.append("activity")
            payload["activity"] = activity

        recent_activity = _shape_recent_activity(blob.get("recent_activity") or [])
        if recent_activity:
            sections.append("recent_activity")
            payload["recent_activity"] = recent_activity

        quick_actions = _quick_actions(
            quote=can_quote,
            customer_create=can_customer_create,
            proposals=can_proposals,
            customers=can_customers,
            policies=can_policies,
            payments=can_payments,
            agents=can_agents,
            products=can_products,
            audit=can_audit,
            claims=can_claims,
            claim_create=can_claim_create,
        )
        if quick_actions:
            sections.append("quick_actions")
            payload["quick_actions"] = quick_actions

        payload["sections"] = sections
        payload["headline"] = headline
        payload["cache"] = {"hit": False, "ttl_s": _CACHE_TTL_S}

        await _cache_set(cache_key, payload)
        return payload


# --- SQL: single round-trip, gated by boolean flags (still RLS-scoped) ---------------

_TENANT_SCOPED_TABLES = (
    "payments",
    "policies",
    "customers",
    "proposals",
    "certificates",
    "intermediaries",
    "insurance_products",
    "audit_events",
    "wallets",
    "claims",
    "claim_followups",
)

_BRANCH_SCOPED_OVERVIEW_TABLES = frozenset(
    {
        "payments",
        "policies",
        "customers",
        "proposals",
        "certificates",
        "intermediaries",
        "claims",
    }
)


_SQL_FOLLOW_KEYWORDS = frozenset(
    {
        "where",
        "group",
        "order",
        "limit",
        "join",
        "left",
        "right",
        "inner",
        "outer",
        "on",
        "and",
        "or",
        "as",
        "from",
        "select",
        "union",
        "case",
        "when",
        "then",
        "else",
        "end",
        "filter",
        "having",
        "natural",
        "cross",
        "full",
    }
)


# Sales Agent logins: only the agent's own sales. Any other branch-scoped table is FALSE.
_AGENT_POLICY_IDS = (
    "(SELECT ap.id FROM policies ap "
    "WHERE ap.tenant_id = CAST(:tenant_id AS uuid) "
    "AND ap.intermediary_id = CAST(:agent_id AS uuid))"
)
_AGENT_TABLE_PREDICATES = {
    "policies": "intermediary_id = CAST(:agent_id AS uuid)",
    "proposals": "intermediary_id = CAST(:agent_id AS uuid)",
    "payments": f"policy_id IN {_AGENT_POLICY_IDS}",
    "customers": (
        "(referred_by_intermediary_id = CAST(:agent_id AS uuid) OR id IN "
        "(SELECT ac.customer_id FROM policies ac "
        "WHERE ac.tenant_id = CAST(:tenant_id AS uuid) "
        "AND ac.intermediary_id = CAST(:agent_id AS uuid)))"
    ),
    "claims": (
        "(created_by_user_id = CAST(:user_id AS uuid) "
        "OR assigned_to_user_id = CAST(:user_id AS uuid) "
        f"OR policy_id IN {_AGENT_POLICY_IDS})"
    ),
}


def _overview_table_predicate(
    table: str,
    branch_scope: BranchScope,
    *,
    platform_wide: bool = False,
    agent: bool = False,
) -> str:
    """Tenant pin plus a fail-closed branch predicate. Table names are allowlisted.

    Platform admins already see every tenant on the claims desk. Pinning
    overview to the platform tenant hid agency claims and follow-ups.
    RLS still applies; ``app.is_platform_admin`` opens those rows.
    """
    if platform_wide:
        return "TRUE"
    where = "tenant_id = CAST(:tenant_id AS uuid)"
    if table not in _BRANCH_SCOPED_OVERVIEW_TABLES:
        return where
    if agent:
        return f"{where} AND {_AGENT_TABLE_PREDICATES.get(table, 'FALSE')}"
    if branch_scope == BranchScope.ALL_TENANT:
        return where
    if branch_scope == BranchScope.ASSIGNED:
        return (
            f"{where} AND branch_id IS NOT NULL "
            "AND branch_id = ANY(CAST(:branch_ids AS uuid[]))"
        )
    return f"{where} AND FALSE"


def _scope_overview_sql(
    sql: str,
    branch_scope: BranchScope = BranchScope.ALL_TENANT,
    *,
    platform_wide: bool = False,
    agent: bool = False,
) -> str:
    """Pin every tenant table even if the session has RLS bypassed.

    ``ALL_TENANT`` / guests omit ``branch_id`` so a missing column cannot 500
    a tenant-wide principal. ``ASSIGNED`` binds a UUID array. ``NONE`` is
    ``FALSE`` — empty assignments are never tenant-wide.

    Aliases are captured only when the next token is not a SQL clause keyword.
    Consuming WHERE/GROUP/ORDER as an alias and then discarding it produced
    `AS payments created_at >= …` (syntax error at created_at).
    """
    tables = "|".join(_TENANT_SCOPED_TABLES)
    keywords = "|".join(sorted(_SQL_FOLLOW_KEYWORDS, key=lambda item: (-len(item), item)))
    pattern = re.compile(
        rf"\b(FROM|JOIN)\s+({tables})\b(?:\s+(?!(?:{keywords})\b)([A-Za-z_][\w]*))?",
        re.IGNORECASE,
    )

    def _repl(match: re.Match[str]) -> str:
        keyword, table, alias = match.group(1), match.group(2), match.group(3)
        where = _overview_table_predicate(
            table, branch_scope, platform_wide=platform_wide, agent=agent
        )
        inner = f"(SELECT * FROM {table} WHERE {where})"
        return f"{keyword} {inner} AS {alias or table}"

    return pattern.sub(_repl, sql)


_OVERVIEW_SQL_TEMPLATE = """
SELECT jsonb_build_object(
  'payments', CASE WHEN :want_payments THEN (
    SELECT jsonb_build_object(
      'initiated', count(*),
      'successful', count(*) FILTER (WHERE status = 'SUCCESS'),
      'pending', count(*) FILTER (WHERE status IN ('PENDING', 'INITIATED')),
      'failed', count(*) FILTER (WHERE status IN ('FAILED', 'CANCELLED')),
      'volume_current', coalesce(sum(amount) FILTER (WHERE status = 'SUCCESS'), 0),
      'currency', coalesce(max(currency) FILTER (WHERE created_at IS NOT NULL), 'KES')
    )
    FROM payments
    WHERE created_at >= :start AND created_at <= :end
  ) END,
  'payments_prior', CASE WHEN :want_payments THEN (
    SELECT coalesce(sum(amount), 0)
    FROM payments
    WHERE created_at >= :compare_start
      AND created_at < :compare_end
      AND status = 'SUCCESS'
  ) END,
  'payments_daily', CASE WHEN :want_payments THEN (
    SELECT coalesce(jsonb_object_agg(day::text, jsonb_build_object('count', c, 'success', s)), '{}'::jsonb)
    FROM (
      SELECT date_trunc('day', created_at)::date AS day,
             count(*) AS c,
             count(*) FILTER (WHERE status = 'SUCCESS') AS s
      FROM payments
      WHERE created_at >= :daily_start AND created_at <= :end
      GROUP BY 1
    ) d
  ) END,
  'premium', CASE WHEN :want_payments THEN (
    SELECT coalesce(jsonb_object_agg(method, total), '{}'::jsonb)
    FROM (
      SELECT method, coalesce(sum(amount), 0) AS total
      FROM payments
      WHERE created_at >= :start AND created_at <= :end AND status = 'SUCCESS'
      GROUP BY method
    ) m
  ) END,
  'premium_growth', CASE WHEN :want_payments THEN (
    SELECT jsonb_build_object(
      'months', coalesce((
        SELECT jsonb_object_agg(to_char(month, 'YYYY-MM'), amount)
        FROM (
          SELECT date_trunc('month', created_at) AS month,
                 coalesce(sum(amount), 0) AS amount
          FROM payments
          WHERE status = 'SUCCESS'
            AND created_at >= :window_start
            AND created_at <= :end
          GROUP BY 1
        ) g
      ), '{}'::jsonb),
      'currency', coalesce((
        SELECT currency FROM payments ORDER BY created_at DESC NULLS LAST LIMIT 1
      ), 'KES')
    )
  ) END,
  'wallet', CASE WHEN :want_wallet THEN (
    SELECT jsonb_build_object(
      'available_balance', coalesce(available_balance, 0),
      'ledger_balance', coalesce(ledger_balance, 0),
      'currency', coalesce(currency, 'KES'),
      'status', coalesce(status, 'ACTIVE')
    )
    FROM wallets
    WHERE tenant_id = CAST(:tenant_id AS uuid)
    LIMIT 1
  ) END,
  'policies', CASE WHEN :want_policies THEN (
    SELECT jsonb_build_object(
      'by_status', coalesce((
        SELECT jsonb_object_agg(status, c) FROM (
          SELECT status, count(*) AS c FROM policies GROUP BY status
        ) s
      ), '{}'::jsonb),
      'created_in_period', count(*) FILTER (WHERE created_at >= :start AND created_at <= :end),
      'cancelled_in_period', count(*) FILTER (
        WHERE status = 'CANCELLED'
          AND cancelled_at IS NOT NULL
          AND cancelled_at >= :start
          AND cancelled_at <= :end
      ),
      'in_force_premium', coalesce(sum(gross_premium) FILTER (WHERE status = 'ACTIVE'), 0),
      'sum_insured', coalesce(sum(sum_insured) FILTER (WHERE status = 'ACTIVE'), 0),
      'expiring_30d', count(*) FILTER (
        WHERE status = 'ACTIVE'
          AND cover_end_date IS NOT NULL
          AND cover_end_date >= :today
          AND cover_end_date <= :soon
      ),
      'top_products', coalesce((
        SELECT jsonb_agg(jsonb_build_object('code', product_code, 'count', c) ORDER BY c DESC)
        FROM (
          SELECT product_code, count(*) AS c
          FROM policies
          WHERE status = 'ACTIVE' AND product_code IS NOT NULL
          GROUP BY product_code
          ORDER BY c DESC
          LIMIT 5
        ) tp
      ), '[]'::jsonb),
      'dow', coalesce((
        SELECT jsonb_object_agg(dow::text, c)
        FROM (
          SELECT extract(dow FROM created_at) AS dow, count(*) AS c
          FROM policies
          WHERE created_at >= :start AND created_at <= :end
          GROUP BY 1
        ) d
      ), '{}'::jsonb),
      'week', coalesce((
        SELECT jsonb_object_agg(day::text, c)
        FROM (
          SELECT date_trunc('day', created_at)::date AS day, count(*) AS c
          FROM policies
          WHERE created_at >= :week_start AND created_at <= :end
          GROUP BY 1
        ) w
      ), '{}'::jsonb)
    )
    FROM policies
  ) END,
  'customers', CASE WHEN :want_customers THEN (
    SELECT jsonb_build_object(
      'total', count(*) FILTER (WHERE deleted_at IS NULL),
      'active', count(*) FILTER (WHERE deleted_at IS NULL AND status = 'ACTIVE'),
      'with_kra', count(*) FILTER (
        WHERE deleted_at IS NULL AND kra_pin IS NOT NULL AND kra_pin <> ''
      ),
      'linked', count(*) FILTER (
        WHERE deleted_at IS NULL
          AND external_client_ref IS NOT NULL
          AND external_client_ref <> ''
      ),
      'created_in_period', count(*) FILTER (
        WHERE deleted_at IS NULL AND created_at >= :start AND created_at <= :end
      ),
      'dow', coalesce((
        SELECT jsonb_object_agg(dow::text, c)
        FROM (
          SELECT extract(dow FROM created_at) AS dow, count(*) AS c
          FROM customers
          WHERE deleted_at IS NULL AND created_at >= :start AND created_at <= :end
          GROUP BY 1
        ) d
      ), '{}'::jsonb),
      'week', coalesce((
        SELECT jsonb_object_agg(day::text, c)
        FROM (
          SELECT date_trunc('day', created_at)::date AS day, count(*) AS c
          FROM customers
          WHERE deleted_at IS NULL AND created_at >= :week_start AND created_at <= :end
          GROUP BY 1
        ) w
      ), '{}'::jsonb)
    )
    FROM customers
  ) END,
  'proposals', CASE WHEN :want_proposals THEN (
    SELECT jsonb_build_object(
      'drafts', count(*) FILTER (
        WHERE status IN ('DRAFT', 'PREMIUM_CALCULATED', 'DOUBLE_INSURANCE_CHECKED', 'SUBMITTED')
      ),
      'approved', count(*) FILTER (WHERE status = 'APPROVED'),
      'converted', count(*) FILTER (WHERE status = 'CONVERTED'),
      'rejected', count(*) FILTER (WHERE status = 'REJECTED'),
      'in_period', count(*) FILTER (WHERE created_at >= :start AND created_at <= :end),
      'converted_in_period', count(*) FILTER (
        WHERE status = 'CONVERTED' AND updated_at >= :start AND updated_at <= :end
      ),
      'double_insurance_hits', count(*) FILTER (WHERE double_insurance_clear IS FALSE),
      'pipeline_premium', coalesce(sum(gross_premium) FILTER (
        WHERE status IN (
          'DRAFT', 'PREMIUM_CALCULATED', 'DOUBLE_INSURANCE_CHECKED', 'SUBMITTED', 'APPROVED'
        )
      ), 0)
    )
    FROM proposals
  ) END,
  'recent_applications', CASE WHEN :want_proposals THEN (
    SELECT coalesce(jsonb_agg(row_to_json(x)::jsonb), '[]'::jsonb)
    FROM (
      SELECT
        p.id::text AS id,
        p.status::text AS status,
        p.product_code,
        p.cover_option,
        p.gross_premium,
        p.created_at,
        p.updated_at,
        trim(both FROM coalesce(c.first_name, '') || ' ' || coalesce(c.last_name, '')) AS customer_name,
        c.avatar_url AS customer_avatar_url
      FROM proposals p
      JOIN customers c ON c.id = p.customer_id
      ORDER BY p.updated_at DESC NULLS LAST
      LIMIT 8
    ) x
  ) END,
  'certificates', CASE WHEN :want_certificates THEN (
    SELECT jsonb_build_object(
      'by_status', coalesce((
        SELECT jsonb_object_agg(status, c) FROM (
          SELECT status, count(*) AS c FROM certificates GROUP BY status
        ) s
      ), '{}'::jsonb),
      'generated_in_period', (
        SELECT count(*)
        FROM certificates
        WHERE status = 'GENERATED'
          AND generated_at IS NOT NULL
          AND generated_at >= :start
          AND generated_at <= :end
      )
    )
  ) END,
  'agents', CASE WHEN :want_agents THEN (
    SELECT jsonb_build_object(
      'by_status', coalesce((
        SELECT jsonb_object_agg(status, c) FROM (
          SELECT status, count(*) AS c FROM intermediaries GROUP BY status
        ) s
      ), '{}'::jsonb),
      'created_in_period', (
        SELECT count(*) FROM intermediaries
        WHERE created_at >= :start AND created_at <= :end
      )
    )
  ) END,
  'products', CASE WHEN :want_products THEN (
    SELECT jsonb_build_object(
      'total', count(*),
      'active', count(*) FILTER (WHERE is_active IS TRUE)
    )
    FROM insurance_products
  ) END,
  'claims', CASE WHEN :want_claims THEN (
    SELECT jsonb_build_object(
      'by_status', coalesce((
        SELECT jsonb_object_agg(status, c) FROM (
          SELECT status, count(*) AS c FROM claims GROUP BY status
        ) s
      ), '{}'::jsonb),
      'open', count(*) FILTER (
        WHERE status NOT IN (
          'VETTING_FAILED', 'DEFINITE_REJECTED', 'REJECTED', 'CANCELLED', 'WITHDRAWN', 'CLOSED'
        )
      ),
      'unassigned', count(*) FILTER (
        WHERE assigned_to_user_id IS NULL
          AND status NOT IN (
            'VETTING_FAILED', 'DEFINITE_REJECTED', 'REJECTED', 'CANCELLED', 'WITHDRAWN', 'CLOSED'
          )
      ),
      'assigned', count(*) FILTER (
        WHERE assigned_to_user_id IS NOT NULL
          AND status NOT IN (
            'VETTING_FAILED', 'DEFINITE_REJECTED', 'REJECTED', 'CANCELLED', 'WITHDRAWN', 'CLOSED'
          )
      ),
      'guest_intake', count(*) FILTER (
        WHERE channel = 'GUEST'
          AND assigned_to_user_id IS NULL
          AND status IN ('CLAIM_SUBMITTED', 'ADDITIONAL_INFORMATION_REQUIRED', 'VETTING')
      ),
      'created_in_period', count(*) FILTER (WHERE created_at >= :start AND created_at <= :end),
      'closed_in_period', count(*) FILTER (
        WHERE closed_at IS NOT NULL AND closed_at >= :start AND closed_at <= :end
      ),
      'claimed_open', coalesce(sum(claimed_amount) FILTER (
        WHERE status NOT IN (
          'VETTING_FAILED', 'DEFINITE_REJECTED', 'REJECTED', 'CANCELLED', 'WITHDRAWN', 'CLOSED'
        )
      ), 0),
      'approved_open', coalesce(sum(approved_amount) FILTER (
        WHERE status IN (
          'DEFINITE_APPROVED', 'PAYMENT_PENDING', 'PAYMENT_AUTHORIZATION',
          'PAYMENT_AUTHORIZED', 'PAYMENT_PROCESSING', 'PAYMENT_REVIEW', 'CLIENT_NOTIFIED'
        )
      ), 0),
      'claimed_intake', coalesce(sum(claimed_amount) FILTER (
        WHERE status IN ('CLAIM_DRAFT', 'CLAIM_SUBMITTED')
      ), 0),
      'claimed_assessing', coalesce(sum(claimed_amount) FILTER (
        WHERE status IN ('VETTING', 'ADDITIONAL_INFORMATION_REQUIRED')
      ), 0),
      'claimed_insurer', coalesce(sum(claimed_amount) FILTER (
        WHERE status IN ('SENT_TO_DEFINITE', 'DEFINITE_REVIEW')
      ), 0),
      'claimed_settling', coalesce(sum(claimed_amount) FILTER (
        WHERE status IN (
          'VETTING_PASSED', 'DEFINITE_APPROVED', 'PAYMENT_PENDING', 'PAYMENT_AUTHORIZATION',
          'PAYMENT_AUTHORIZED', 'PAYMENT_PROCESSING', 'PAYMENT_COMPLETED', 'PAYMENT_FAILED',
          'PAYMENT_REVIEW', 'CLIENT_NOTIFIED'
        )
      ), 0),
      'guest_open', count(*) FILTER (
        WHERE channel = 'GUEST'
          AND status NOT IN (
            'VETTING_FAILED', 'DEFINITE_REJECTED', 'REJECTED', 'CANCELLED', 'WITHDRAWN', 'CLOSED'
          )
      ),
      'currency', coalesce(max(currency), 'KES'),
      'week', coalesce((
        SELECT jsonb_object_agg(day::text, c)
        FROM (
          SELECT date_trunc('day', created_at)::date AS day, count(*) AS c
          FROM claims
          WHERE created_at >= :week_start AND created_at <= :end
          GROUP BY 1
        ) w
      ), '{}'::jsonb),
      'recent', coalesce((
        SELECT jsonb_agg(row_to_json(x)::jsonb)
        FROM (
          SELECT
            cl.id::text AS id,
            cl.claim_number,
            cl.status::text AS status,
            cl.channel,
            cl.claimed_amount,
            cl.approved_amount,
            cl.currency,
            cl.vehicle_registration,
            (cl.assigned_to_user_id IS NOT NULL) AS assigned,
            u.full_name AS assigned_to_name,
            trim(both FROM coalesce(cu.first_name, '') || ' ' || coalesce(cu.last_name, '')) AS customer_name,
            cl.updated_at
          FROM claims cl
          LEFT JOIN customers cu ON cu.id = cl.customer_id
          LEFT JOIN users u ON u.id = cl.assigned_to_user_id
          ORDER BY cl.updated_at DESC NULLS LAST
          LIMIT 6
        ) x
      ), '[]'::jsonb)
    )
    FROM claims
  ) END,
  'followups', CASE WHEN :want_claims THEN (
    SELECT jsonb_build_object(
      'total', count(*),
      'open', count(*) FILTER (
        WHERE f.status IN ('OPEN', 'PENDING_CLIENT', 'PENDING_INTERNAL')
      ),
      'overdue', count(*) FILTER (
        WHERE f.status IN ('OPEN', 'PENDING_CLIENT', 'PENDING_INTERNAL')
          AND f.due_at IS NOT NULL
          AND f.due_at < :end
      ),
      'due_soon', count(*) FILTER (
        WHERE f.status IN ('OPEN', 'PENDING_CLIENT', 'PENDING_INTERNAL')
          AND f.due_at IS NOT NULL
          AND f.due_at >= :end
          AND f.due_at <= :followup_soon
      ),
      'waiting_client', count(*) FILTER (WHERE f.status = 'PENDING_CLIENT'),
      'waiting_desk', count(*) FILTER (WHERE f.status IN ('OPEN', 'PENDING_INTERNAL')),
      'completed_in_period', count(*) FILTER (
        WHERE f.status = 'COMPLETED'
          AND f.completed_at IS NOT NULL
          AND f.completed_at >= :start
          AND f.completed_at <= :end
      ),
      'created_in_period', count(*) FILTER (
        WHERE f.created_at >= :start AND f.created_at <= :end
      ),
      'by_type', coalesce((
        SELECT jsonb_agg(jsonb_build_object('type', followup_type, 'count', c) ORDER BY c DESC)
        FROM (
          SELECT f2.followup_type, count(*) AS c
          FROM claim_followups f2
          JOIN claims c2 ON c2.id = f2.claim_id
          WHERE f2.status IN ('OPEN', 'PENDING_CLIENT', 'PENDING_INTERNAL')
          GROUP BY f2.followup_type
          ORDER BY c DESC
          LIMIT 5
        ) t
      ), '[]'::jsonb),
      'recent', coalesce((
        SELECT jsonb_agg(row_to_json(x)::jsonb)
        FROM (
          SELECT
            f3.id::text AS id,
            f3.subject,
            f3.followup_type,
            f3.status::text AS status,
            f3.due_at,
            cl.id::text AS claim_id,
            cl.claim_number,
            trim(both FROM coalesce(cu.first_name, '') || ' ' || coalesce(cu.last_name, '')) AS customer_name,
            (f3.due_at IS NOT NULL AND f3.due_at < :end) AS overdue
          FROM claim_followups f3
          JOIN claims cl ON cl.id = f3.claim_id
          LEFT JOIN customers cu ON cu.id = cl.customer_id
          WHERE f3.status IN ('OPEN', 'PENDING_CLIENT', 'PENDING_INTERNAL')
          ORDER BY
            CASE WHEN f3.due_at IS NOT NULL AND f3.due_at < :end THEN 0 ELSE 1 END,
            f3.due_at ASC NULLS LAST,
            f3.created_at DESC
          LIMIT 6
        ) x
      ), '[]'::jsonb)
    )
    FROM claim_followups f
    JOIN claims c ON c.id = f.claim_id
  ) END,
  'activity', CASE WHEN :want_activity THEN (
    SELECT coalesce(jsonb_object_agg(month_key, c), '{}'::jsonb)
    FROM (
      SELECT to_char(month, 'YYYY-MM') AS month_key, sum(c)::int AS c
      FROM (
        SELECT date_trunc('month', created_at) AS month, count(*) AS c
        FROM payments
        WHERE :want_payments AND created_at >= :window_start AND created_at <= :end
        GROUP BY 1
        UNION ALL
        SELECT date_trunc('month', created_at), count(*)
        FROM policies
        WHERE :want_policies AND created_at >= :window_start AND created_at <= :end
        GROUP BY 1
        UNION ALL
        SELECT date_trunc('month', created_at), count(*)
        FROM customers
        WHERE :want_customers
          AND deleted_at IS NULL
          AND created_at >= :window_start
          AND created_at <= :end
        GROUP BY 1
        UNION ALL
        SELECT date_trunc('month', created_at), count(*)
        FROM proposals
        WHERE :want_proposals AND created_at >= :window_start AND created_at <= :end
        GROUP BY 1
        UNION ALL
        SELECT date_trunc('month', created_at), count(*)
        FROM claims
        WHERE :want_claims AND created_at >= :window_start AND created_at <= :end
        GROUP BY 1
      ) u
      GROUP BY 1
    ) a
  ) END,
  'recent_activity', CASE
    WHEN :want_audit THEN (
      SELECT coalesce(jsonb_agg(row_to_json(x)::jsonb), '[]'::jsonb)
      FROM (
        SELECT
          e.id::text AS id,
          'audit' AS kind,
          e.action,
          e.resource,
          e.result,
          replace(replace(e.action, '.', ' · '), '_', ' ') AS title,
          e.resource || CASE
            WHEN e.resource_id IS NOT NULL AND e.resource_id <> ''
              THEN ' · ' || left(e.resource_id, 8)
            ELSE ''
          END AS detail,
          u.full_name AS actor_name,
          u.avatar_url AS actor_avatar_url,
          e.created_at
        FROM audit_events e
        LEFT JOIN users u ON u.id = e.user_id
        ORDER BY e.created_at DESC NULLS LAST
        LIMIT 8
      ) x
    )
    ELSE (
      SELECT coalesce(jsonb_agg(row_to_json(x)::jsonb ORDER BY x.created_at DESC NULLS LAST), '[]'::jsonb)
      FROM (
        SELECT * FROM (
          SELECT
            'proposal-' || p.id::text AS id,
            'proposal' AS kind,
            'proposal.updated' AS action,
            'proposal' AS resource,
            'SUCCESS' AS result,
            'Proposal updated' AS title,
            p.product_code || ' · ' || p.status::text AS detail,
            u.full_name AS actor_name,
            u.avatar_url AS actor_avatar_url,
            p.updated_at AS created_at
          FROM proposals p
          LEFT JOIN users u ON u.id = p.created_by_user_id
          WHERE :want_proposals
          ORDER BY p.updated_at DESC NULLS LAST
          LIMIT 8
        ) p
        UNION ALL
        SELECT * FROM (
          SELECT
            'payment-' || pay.id::text,
            'payment',
            'payment.created',
            'payment',
            'SUCCESS',
            'Payment recorded',
            pay.status::text || ' · ' || trim(to_char(coalesce(pay.amount, 0), '999999999990')) || ' ' || coalesce(pay.currency, 'KES'),
            u.full_name,
            u.avatar_url,
            pay.created_at
          FROM payments pay
          LEFT JOIN users u ON u.id = pay.initiated_by_user_id
          WHERE :want_payments
          ORDER BY pay.created_at DESC NULLS LAST
          LIMIT 8
        ) pay
        UNION ALL
        SELECT * FROM (
          SELECT
            'policy-' || pol.id::text,
            'policy',
            'policy.created',
            'policy',
            'SUCCESS',
            'Policy recorded',
            pol.product_code || ' · ' || pol.status::text,
            u.full_name,
            u.avatar_url,
            pol.created_at
          FROM policies pol
          LEFT JOIN users u ON u.id = pol.created_by_user_id
          WHERE :want_policies
          ORDER BY pol.created_at DESC NULLS LAST
          LIMIT 8
        ) pol
        UNION ALL
        SELECT * FROM (
          SELECT
            'claim-' || cl.id::text,
            'claim',
            'claim.updated',
            'claim',
            'SUCCESS',
            'Claim ' || cl.claim_number,
            cl.status::text,
            u.full_name,
            u.avatar_url,
            cl.updated_at
          FROM claims cl
          LEFT JOIN users u ON u.id = cl.assigned_to_user_id
          WHERE :want_claims
          ORDER BY cl.updated_at DESC NULLS LAST
          LIMIT 8
        ) cl
        UNION ALL
        SELECT * FROM (
          SELECT
            'customer-' || c.id::text,
            'customer',
            'customer.created',
            'customer',
            'SUCCESS',
            'Customer recorded',
            nullif(trim(both FROM coalesce(c.first_name, '') || ' ' || coalesce(c.last_name, '')), ''),
            nullif(trim(both FROM coalesce(c.first_name, '') || ' ' || coalesce(c.last_name, '')), ''),
            c.avatar_url,
            c.created_at
          FROM customers c
          WHERE :want_customers AND c.deleted_at IS NULL
          ORDER BY c.created_at DESC NULLS LAST
          LIMIT 8
        ) c
      ) x
      LIMIT 8
    )
  END
) AS payload
"""

_OVERVIEW_SQL_BY_SCOPE = {
    scope: _scope_overview_sql(_OVERVIEW_SQL_TEMPLATE, scope)
    for scope in (BranchScope.ALL_TENANT, BranchScope.ASSIGNED, BranchScope.NONE)
}
_OVERVIEW_SQL = _OVERVIEW_SQL_BY_SCOPE[BranchScope.ALL_TENANT]
_OVERVIEW_SQL_PLATFORM = _scope_overview_sql(
    _OVERVIEW_SQL_TEMPLATE, BranchScope.ALL_TENANT, platform_wide=True
)
_OVERVIEW_SQL_AGENT = _scope_overview_sql(
    _OVERVIEW_SQL_TEMPLATE, BranchScope.ALL_TENANT, agent=True
)


def _overview_statement(
    branch_scope: BranchScope, *, platform_wide: bool = False, agent: bool = False
):
    if agent:
        return text(_OVERVIEW_SQL_AGENT)
    sql = (
        _OVERVIEW_SQL_PLATFORM
        if platform_wide
        else _OVERVIEW_SQL_BY_SCOPE[branch_scope]
    )
    stmt = text(sql)
    if not platform_wide and branch_scope == BranchScope.ASSIGNED:
        return stmt.bindparams(bindparam("branch_ids", type_=ARRAY(PGUUID(as_uuid=True))))
    return stmt


# --- Shapers ------------------------------------------------------------------------


def _shape_payments_full(
    payments: dict[str, Any],
    prior: Any,
    daily_map: dict[str, Any] | None,
    *,
    days: int,
    daily_start: datetime,
) -> dict[str, Any]:
    initiated = int(payments.get("initiated") or 0)
    successful = int(payments.get("successful") or 0)
    pending = int(payments.get("pending") or 0)
    failed = int(payments.get("failed") or 0)
    volume_current = _money(payments.get("volume_current"))
    volume_prior = _money(prior)
    success_rate = round((successful / initiated) * 100) if initiated else 0
    currency = payments.get("currency") or "KES"
    daily: list[dict[str, Any]] = []
    for i in range(days):
        day = (daily_start + timedelta(days=i)).date().isoformat()
        cell = (daily_map or {}).get(day) or {}
        if isinstance(cell, dict):
            daily.append(
                {
                    "date": day,
                    "count": int(cell.get("count") or 0),
                    "success": int(cell.get("success") or 0),
                }
            )
        else:
            daily.append({"date": day, "count": 0, "success": 0})
    delta_pct = (
        round(((volume_current - volume_prior) / volume_prior) * 100)
        if volume_prior > 0
        else (100 if volume_current > 0 else 0)
    )
    return {
        "initiated": initiated,
        "successful": successful,
        "pending": pending,
        "failed": failed,
        "success_rate": success_rate,
        "volume": volume_current,
        "volume_prior": volume_prior,
        "volume_delta_pct": delta_pct,
        "currency": currency,
        "daily": daily,
    }


def _shape_premium(by_method: dict[str, Any], payments: dict[str, Any]) -> dict[str, Any]:
    gross = payments["volume"]
    online = _money(by_method.get("MPESA")) + _money(by_method.get("CARD"))
    wallet = _money(by_method.get("WALLET"))
    bank = _money(by_method.get("BANK"))
    other = max(0.0, gross - online - wallet - bank)
    settled = payments["successful"]

    def share(amount: float) -> int:
        return round((amount / gross) * 100) if gross > 0 else 0

    return {
        "gross": gross,
        "avg": (gross / settled) if settled else 0.0,
        "settled": settled,
        "currency": payments["currency"],
        "volume_delta_pct": payments["volume_delta_pct"],
        "channels": [
            {"key": "online", "label": "M-Pesa / card", "amount": online, "share": share(online)},
            {"key": "wallet", "label": "Wallet", "amount": wallet, "share": share(wallet)},
            {"key": "bank", "label": "Bank", "amount": bank, "share": share(bank)},
            {"key": "other", "label": "Other", "amount": other, "share": share(other)},
        ],
        "wallet_balance": None,
    }


def _shape_wallet(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {
            "available_balance": 0.0,
            "ledger_balance": 0.0,
            "currency": "KES",
            "status": "ACTIVE",
        }
    return {
        "available_balance": _money(raw.get("available_balance")),
        "ledger_balance": _money(raw.get("ledger_balance")),
        "currency": raw.get("currency") or "KES",
        "status": raw.get("status") or "ACTIVE",
    }


def _shape_policies(raw: dict[str, Any], *, end: datetime) -> dict[str, Any]:
    by_status = {str(k): int(v or 0) for k, v in (raw.get("by_status") or {}).items()}
    total = sum(by_status.values())
    active = by_status.get("ACTIVE", 0)
    in_force = _money(raw.get("in_force_premium"))
    return {
        "total": total,
        "active": active,
        "pending_payment": by_status.get("PENDING_PAYMENT", 0),
        "pending_certificate": by_status.get("PENDING_CERTIFICATE", 0),
        "cancelled": by_status.get("CANCELLED", 0),
        "expired": by_status.get("EXPIRED", 0),
        "created_in_period": int(raw.get("created_in_period") or 0),
        "cancelled_in_period": int(raw.get("cancelled_in_period") or 0),
        "in_force_premium": in_force,
        "sum_insured": _money(raw.get("sum_insured")),
        "avg_in_force_premium": (in_force / active) if active else 0.0,
        "expiring_30d": int(raw.get("expiring_30d") or 0),
        "top_products": [
            {"code": str(p.get("code")), "count": int(p.get("count") or 0)}
            for p in (raw.get("top_products") or [])
            if p and p.get("code")
        ],
        "currency": "KES",
        "peak_weekday": _peak_weekday_from_map(raw.get("dow")),
        "week": _week_from_map(end, raw.get("week")),
    }


def _shape_customers(raw: dict[str, Any], *, end: datetime) -> dict[str, Any]:
    return {
        "total": int(raw.get("total") or 0),
        "active": int(raw.get("active") or 0),
        "with_kra": int(raw.get("with_kra") or 0),
        "linked": int(raw.get("linked") or 0),
        "created_in_period": int(raw.get("created_in_period") or 0),
        "peak_weekday": _peak_weekday_from_map(raw.get("dow")),
        "week": _week_from_map(end, raw.get("week")),
    }


_CLAIM_CLOSED = frozenset(
    {
        "VETTING_FAILED",
        "DEFINITE_REJECTED",
        "REJECTED",
        "CANCELLED",
        "WITHDRAWN",
        "CLOSED",
    }
)
_CLAIM_INTAKE = frozenset({"CLAIM_DRAFT", "CLAIM_SUBMITTED"})
_CLAIM_ASSESS = frozenset({"VETTING", "ADDITIONAL_INFORMATION_REQUIRED"})
_CLAIM_INSURER = frozenset({"SENT_TO_DEFINITE", "DEFINITE_REVIEW"})
_CLAIM_SETTLE = frozenset(
    {
        "VETTING_PASSED",
        "DEFINITE_APPROVED",
        "PAYMENT_PENDING",
        "PAYMENT_AUTHORIZATION",
        "PAYMENT_AUTHORIZED",
        "PAYMENT_PROCESSING",
        "PAYMENT_COMPLETED",
        "PAYMENT_FAILED",
        "PAYMENT_REVIEW",
        "CLIENT_NOTIFIED",
    }
)
_FOLLOWUP_TYPE_LABELS = {
    "CLIENT_INFORMATION": "Client",
    "DOCUMENT_REQUIRED": "Documents",
    "MEDICAL_INFORMATION": "Medical",
    "POLICE_DOCUMENT": "Police",
    "PAYMENT_INFORMATION": "Payment",
    "INTERNAL_REVIEW": "Internal",
    "OTHER": "Other",
}


def _count_statuses(by_status: dict[str, int], keys: frozenset[str]) -> int:
    return sum(by_status.get(key, 0) for key in keys)


def _shape_recent_claims(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": str(row.get("id")),
                "claim_number": row.get("claim_number") or "",
                "status": str(row.get("status") or ""),
                "channel": str(row.get("channel") or "STAFF"),
                "claimed_amount": _money(row.get("claimed_amount")),
                "approved_amount": _money(row.get("approved_amount")) if row.get("approved_amount") is not None else None,
                "currency": row.get("currency") or "KES",
                "vehicle_registration": row.get("vehicle_registration"),
                "assigned": bool(row.get("assigned")),
                "assigned_to_name": row.get("assigned_to_name"),
                "customer_name": row.get("customer_name") or "",
                "updated_at": _iso(row.get("updated_at")),
            }
        )
    return out


def _shape_recent_followups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        kind = str(row.get("followup_type") or "")
        out.append(
            {
                "id": str(row.get("id")),
                "subject": row.get("subject") or "",
                "type": kind,
                "label": _FOLLOWUP_TYPE_LABELS.get(kind, kind.replace("_", " ").title()),
                "status": str(row.get("status") or ""),
                "due_at": _iso(row.get("due_at")),
                "claim_id": str(row.get("claim_id") or ""),
                "claim_number": row.get("claim_number") or "",
                "customer_name": row.get("customer_name") or "",
                "overdue": bool(row.get("overdue")),
            }
        )
    return out


def _shape_claims(raw: dict[str, Any], *, end: datetime) -> dict[str, Any]:
    by_status = {str(k): int(v or 0) for k, v in (raw.get("by_status") or {}).items()}
    total = sum(by_status.values())
    closed = _count_statuses(by_status, _CLAIM_CLOSED)
    intake = _count_statuses(by_status, _CLAIM_INTAKE)
    assessing = _count_statuses(by_status, _CLAIM_ASSESS)
    with_insurer = _count_statuses(by_status, _CLAIM_INSURER)
    settling = _count_statuses(by_status, _CLAIM_SETTLE)
    currency = raw.get("currency") or "KES"
    queues = [
        {"key": "intake", "label": "Intake", "count": intake, "amount": _money(raw.get("claimed_intake"))},
        {"key": "assessing", "label": "Assessing", "count": assessing, "amount": _money(raw.get("claimed_assessing"))},
        {"key": "insurer", "label": "With insurer", "count": with_insurer, "amount": _money(raw.get("claimed_insurer"))},
        {"key": "settling", "label": "Settling", "count": settling, "amount": _money(raw.get("claimed_settling"))},
    ]
    return {
        "total": total,
        "open": int(raw.get("open") or max(0, total - closed)),
        "unassigned": int(raw.get("unassigned") or 0),
        "assigned": int(
            raw["assigned"]
            if raw.get("assigned") is not None
            else max(0, int(raw.get("open") or max(0, total - closed)) - int(raw.get("unassigned") or 0))
        ),
        "guest_intake": int(raw.get("guest_intake") or 0),
        "guest_open": int(raw.get("guest_open") or 0),
        "intake": intake,
        "assessing": assessing,
        "with_insurer": with_insurer,
        "settling": settling,
        "closed": closed,
        "created_in_period": int(raw.get("created_in_period") or 0),
        "closed_in_period": int(raw.get("closed_in_period") or 0),
        "claimed_open": _money(raw.get("claimed_open")),
        "approved_open": _money(raw.get("approved_open")),
        "currency": currency,
        "queues": queues,
        "recent": _shape_recent_claims(raw.get("recent") or []),
        "week": _week_from_map(end, raw.get("week")),
    }


def _shape_followups(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "total": int(raw.get("total") or 0),
        "open": int(raw.get("open") or 0),
        "overdue": int(raw.get("overdue") or 0),
        "due_soon": int(raw.get("due_soon") or 0),
        "waiting_client": int(raw.get("waiting_client") or 0),
        "waiting_desk": int(raw.get("waiting_desk") or 0),
        "completed_in_period": int(raw.get("completed_in_period") or 0),
        "created_in_period": int(raw.get("created_in_period") or 0),
        "by_type": [
            {
                "type": str(row.get("type")),
                "label": _FOLLOWUP_TYPE_LABELS.get(str(row.get("type")), str(row.get("type") or "").replace("_", " ").title()),
                "count": int(row.get("count") or 0),
            }
            for row in (raw.get("by_type") or [])
            if row and row.get("type")
        ],
        "recent": _shape_recent_followups(raw.get("recent") or []),
    }


def _shape_proposals(raw: dict[str, Any]) -> dict[str, Any]:
    drafts = int(raw.get("drafts") or 0)
    approved = int(raw.get("approved") or 0)
    in_period = int(raw.get("in_period") or 0)
    converted_in_period = int(raw.get("converted_in_period") or 0)
    in_pipeline = drafts + approved
    return {
        "created_in_period": in_period,
        "drafts": drafts,
        "approved": approved,
        "converted": int(raw.get("converted") or 0),
        "rejected": int(raw.get("rejected") or 0),
        "converted_in_period": converted_in_period,
        "double_insurance_hits": int(raw.get("double_insurance_hits") or 0),
        "pipeline_premium": _money(raw.get("pipeline_premium")),
        "in_pipeline": in_pipeline,
        "issuance_pct": round((approved / in_pipeline) * 100) if in_pipeline else 0,
        "conversion_pct": round((converted_in_period / in_period) * 100) if in_period else 0,
        "currency": "KES",
    }


def _shape_certificates(raw: dict[str, Any]) -> dict[str, Any]:
    by_status = {str(k): int(v or 0) for k, v in (raw.get("by_status") or {}).items()}
    return {
        "total": sum(by_status.values()),
        "generated": by_status.get("GENERATED", 0),
        "pending": by_status.get("PENDING", 0),
        "failed": by_status.get("FAILED", 0),
        "revoked": by_status.get("REVOKED", 0),
        "generated_in_period": int(raw.get("generated_in_period") or 0),
    }


def _shape_agents(raw: dict[str, Any]) -> dict[str, Any]:
    by_status = {str(k): int(v or 0) for k, v in (raw.get("by_status") or {}).items()}
    return {
        "total": sum(by_status.values()),
        "approved": by_status.get("APPROVED", 0),
        "pending": by_status.get("PENDING", 0),
        "suspended": by_status.get("SUSPENDED", 0),
        "rejected": by_status.get("REJECTED", 0),
        "created_in_period": int(raw.get("created_in_period") or 0),
    }


def _shape_products(raw: dict[str, Any]) -> dict[str, Any]:
    return {"total": int(raw.get("total") or 0), "active": int(raw.get("active") or 0)}


def _shape_growth(raw: dict[str, Any], month_keys: list[tuple[int, int]]) -> dict[str, Any]:
    months = _fill_months_amount(month_keys, raw.get("months"))
    amounts = [m["amount"] for m in months]
    latest = amounts[-1] if amounts else 0.0
    prior = amounts[-2] if len(amounts) > 1 else 0.0
    peak = max(amounts) if amounts else 0.0
    total = sum(amounts)
    delta_pct = (
        round(((latest - prior) / prior) * 100) if prior > 0 else (100 if latest > 0 else 0)
    )
    return {
        "months": months,
        "latest": latest,
        "prior": prior,
        "peak": peak,
        "total_6mo": total,
        "delta_pct": delta_pct,
        "currency": raw.get("currency") or "KES",
    }


def _shape_activity(raw: dict[str, Any], month_keys: list[tuple[int, int]]) -> dict[str, Any]:
    months = _fill_months_count(month_keys, raw)
    totals = [m["count"] for m in months]
    latest = totals[-1] if totals else 0
    peak = max(totals) if totals else 0
    prior = totals[-2] if len(totals) > 1 else 0
    total_6mo = sum(totals)
    delta_pct = (
        round(((latest - prior) / prior) * 100) if prior > 0 else (100 if latest > 0 else 0)
    )
    of_peak = round((latest / peak) * 100) if peak else 0
    return {
        "months": months,
        "latest": latest,
        "peak": peak,
        "prior": prior,
        "total_6mo": total_6mo,
        "delta_pct": delta_pct,
        "of_peak_pct": of_peak,
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(value)


def _shape_recent_applications(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": str(row.get("id")),
                "status": str(row.get("status")),
                "product_code": row.get("product_code"),
                "cover_option": row.get("cover_option"),
                "gross_premium": _money(row.get("gross_premium")),
                "currency": "KES",
                "customer_name": row.get("customer_name") or "",
                "customer_avatar_url": row.get("customer_avatar_url"),
                "created_at": _iso(row.get("created_at")),
                "updated_at": _iso(row.get("updated_at")),
            }
        )
    return out


def _shape_recent_activity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": str(row.get("id")),
                "kind": row.get("kind"),
                "action": row.get("action"),
                "resource": row.get("resource"),
                "result": row.get("result"),
                "title": row.get("title"),
                "detail": row.get("detail"),
                "actor_name": row.get("actor_name"),
                "actor_avatar_url": row.get("actor_avatar_url"),
                "created_at": _iso(row.get("created_at")),
            }
        )
    return out


def _quick_actions(
    *,
    quote: bool,
    customer_create: bool,
    proposals: bool,
    customers: bool,
    policies: bool,
    payments: bool,
    agents: bool,
    products: bool,
    audit: bool,
    claims: bool = False,
    claim_create: bool = False,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if quote:
        actions.append({"key": "quote", "label": "New quote", "href": "/app/quote", "tone": "primary"})
    if customer_create:
        actions.append(
            {"key": "customer", "label": "Add customer", "href": "/app/customers", "tone": "default"}
        )
    if proposals:
        actions.append(
            {
                "key": "proposals",
                "label": "Review proposals",
                "href": "/app/proposals",
                "tone": "default",
            }
        )
    if policies:
        actions.append(
            {"key": "policies", "label": "Open policies", "href": "/app/policies", "tone": "default"}
        )
    if claim_create:
        actions.append(
            {"key": "claim_new", "label": "Open claim", "href": "/app/claims/new", "tone": "default"}
        )
    if claims:
        actions.append(
            {"key": "claims", "label": "Open claims", "href": "/app/claims", "tone": "default"}
        )
    if payments:
        actions.append(
            {"key": "payments", "label": "Open payments", "href": "/app/payments", "tone": "default"}
        )
    if customers and not customer_create:
        actions.append(
            {
                "key": "customers",
                "label": "Browse customers",
                "href": "/app/customers",
                "tone": "default",
            }
        )
    if agents:
        actions.append(
            {
                "key": "agents",
                "label": "Intermediaries",
                "href": "/app/intermediaries",
                "tone": "default",
            }
        )
    if products:
        actions.append(
            {"key": "products", "label": "Products", "href": "/app/products", "tone": "default"}
        )
    if audit:
        actions.append({"key": "audit", "label": "Audit log", "href": "/app/audit", "tone": "default"})
    return actions[:8]

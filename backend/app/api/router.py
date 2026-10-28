"""API router aggregation."""

from fastapi import APIRouter

from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.branches.router import router as branches_router
from app.modules.certificates.router import router as certificates_router
from app.modules.claims.guest_router import router as guest_claims_router
from app.modules.claims.router import router as claims_router
from app.modules.claims.webhooks import webhook_router as claim_webhooks_router
from app.modules.commissions.router import router as commissions_router
from app.modules.customers.router import router as customers_router
from app.modules.guest.router import router as guest_router
from app.modules.intermediaries.guest_router import router as guest_agents_router
from app.modules.insurance.router import router as insurance_router
from app.modules.intermediaries.router import router as intermediaries_router
from app.modules.jobs.router import router as jobs_router
from app.modules.meta.router import router as meta_router
from app.modules.notifications.router import router as notifications_router
from app.modules.overview.router import router as overview_router
from app.modules.payments.router import router as payments_router
from app.modules.payments.router import webhook_router as payment_webhooks_router
from app.modules.platform.router import router as platform_router
from app.modules.policies.router import router as policies_router
from app.modules.products.router import router as products_router
from app.modules.proposals.router import router as proposals_router
from app.modules.reference.router import router as reference_router
from app.modules.referrals.router import router as referrals_router
from app.modules.reports.router import router as reports_router
from app.modules.roles.router import router as roles_router
from app.modules.system_config.router import router as system_config_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router
from app.modules.ussd.router_admin import router as ussd_admin_router
from app.modules.ussd.router_callback import router as ussd_callback_router
from app.modules.wallets.router import router as wallets_router

api_router = APIRouter()
api_router.include_router(meta_router)
api_router.include_router(auth_router)
api_router.include_router(overview_router)
api_router.include_router(system_config_router)
api_router.include_router(reference_router)
api_router.include_router(roles_router)
api_router.include_router(users_router)
api_router.include_router(branches_router)
api_router.include_router(tenants_router)
api_router.include_router(platform_router)
api_router.include_router(jobs_router)
api_router.include_router(customers_router)
api_router.include_router(intermediaries_router)
api_router.include_router(commissions_router)
api_router.include_router(referrals_router)
api_router.include_router(products_router)
api_router.include_router(guest_router)
api_router.include_router(guest_claims_router)
api_router.include_router(guest_agents_router)
api_router.include_router(insurance_router)
api_router.include_router(proposals_router)
api_router.include_router(policies_router)
api_router.include_router(payments_router)
api_router.include_router(payment_webhooks_router)
api_router.include_router(wallets_router)
api_router.include_router(certificates_router)
api_router.include_router(claims_router)
api_router.include_router(claim_webhooks_router)
api_router.include_router(notifications_router)
api_router.include_router(reports_router)
api_router.include_router(ussd_callback_router)
api_router.include_router(ussd_admin_router)
api_router.include_router(audit_router)

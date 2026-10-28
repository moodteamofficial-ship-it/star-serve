# Production RLS note:
# ENABLE ROW LEVEL SECURITY does not apply to the table owner unless
# FORCE ROW LEVEL SECURITY is set. Production must:
# 1) migrate as owner/migrator role
# 2) run the app as a non-owner role with GRANT SELECT/INSERT/UPDATE/DELETE
# 3) ALTER TABLE ... FORCE ROW LEVEL SECURITY
# Until then, application-level TenantAwareRepository + SecurityContext remain mandatory.

FROM postgres:16-alpine
# placeholder for custom init scripts if needed

Layout: `{tenant_id}/{policy_id}/{certificate_id}.pdf`

DB column: `certificates.local_file_path` (relative path only — never absolute).

Access truth: every store / view / download is logged in `certificate_file_accesses`
(who, what, when, IP, user-agent, local_file_path snapshot).

Serve only via authenticated `/certificates/{id}/download?disposition=inline|attachment`.

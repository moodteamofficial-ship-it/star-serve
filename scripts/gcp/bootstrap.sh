#!/usr/bin/env bash
# Enable APIs, Artifact Registry, runtime service accounts, and IAM.
# Does not print or upload secrets. Run sync-secrets.sh after this.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"

log "Project ${GCP_PROJECT} region ${GCP_REGION}"

log "Enabling APIs"
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="${GCP_PROJECT}"

if ! gcloud artifacts repositories describe "${AR_REPO}" \
  --location="${GCP_REGION}" --project="${GCP_PROJECT}" >/dev/null 2>&1; then
  log "Creating Artifact Registry ${AR_REPO}"
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${GCP_REGION}" \
    --description="Star Serve API images" \
    --project="${GCP_PROJECT}"
else
  log "Artifact Registry ${AR_REPO} already exists"
fi

PROJECT_NUMBER="$(gcloud projects describe "${GCP_PROJECT}" --format='value(projectNumber)')"
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
RUN_AGENT="service-${PROJECT_NUMBER}@serverless-robot-prod.iam.gserviceaccount.com"

ensure_sa() {
  local sa_id="$1"
  local display="$2"
  if gcloud iam service-accounts describe "${sa_id}@${GCP_PROJECT}.iam.gserviceaccount.com" \
    --project="${GCP_PROJECT}" >/dev/null 2>&1; then
    log "Service account ${sa_id} exists"
    return
  fi
  log "Creating service account ${sa_id}"
  gcloud iam service-accounts create "${sa_id}" \
    --display-name="${display}" \
    --project="${GCP_PROJECT}"
}

ensure_sa "$(runtime_sa_id staging)" "Star Serve API staging"
ensure_sa "$(runtime_sa_id production)" "Star Serve API production"
ensure_sa "starserve-deploy" "Star Serve Cloud Build / GitHub deploy"

bind_project() {
  local member="$1"
  local role="$2"
  gcloud projects add-iam-policy-binding "${GCP_PROJECT}" \
    --member="${member}" \
    --role="${role}" \
    --condition=None \
    --quiet >/dev/null
}

log "Granting deploy identities permission to push images and update Cloud Run"
for member in \
  "serviceAccount:${CLOUDBUILD_SA}" \
  "serviceAccount:starserve-deploy@${GCP_PROJECT}.iam.gserviceaccount.com" \
  "serviceAccount:${COMPUTE_SA}"; do
  bind_project "${member}" "roles/run.admin"
  bind_project "${member}" "roles/iam.serviceAccountUser"
  bind_project "${member}" "roles/artifactregistry.writer"
  bind_project "${member}" "roles/cloudbuild.builds.editor"
  bind_project "${member}" "roles/secretmanager.viewer"
  bind_project "${member}" "roles/logging.logWriter"
done

# Runtime SAs: least privilege — only what the process needs at request time.
for env in staging production; do
  sa="serviceAccount:$(runtime_sa "$env")"
  bind_project "${sa}" "roles/logging.logWriter"
  bind_project "${sa}" "roles/cloudtrace.agent"
  gcloud iam service-accounts add-iam-policy-binding "$(runtime_sa "$env")" \
    --member="serviceAccount:${CLOUDBUILD_SA}" \
    --role="roles/iam.serviceAccountUser" \
    --project="${GCP_PROJECT}" \
    --quiet >/dev/null
  gcloud iam service-accounts add-iam-policy-binding "$(runtime_sa "$env")" \
    --member="serviceAccount:starserve-deploy@${GCP_PROJECT}.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser" \
    --project="${GCP_PROJECT}" \
    --quiet >/dev/null
done

# Cloud Run service agent needs to mount secrets into revisions.
gcloud projects add-iam-policy-binding "${GCP_PROJECT}" \
  --member="serviceAccount:${RUN_AGENT}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None \
  --quiet >/dev/null || true

# Private app files (certificates, claim docs, mail PDFs, avatars) in GCS.
GCS_BUCKET="${GCS_BUCKET:-star_serve}"
if gcloud storage buckets describe "gs://${GCS_BUCKET}" --project="${GCP_PROJECT}" >/dev/null 2>&1; then
  log "Granting runtime SAs objectAdmin on gs://${GCS_BUCKET} (bucket stays non-public)"
  for env in staging production; do
    gcloud storage buckets add-iam-policy-binding "gs://${GCS_BUCKET}" \
      --member="serviceAccount:$(runtime_sa "$env")" \
      --role="roles/storage.objectAdmin" \
      --project="${GCP_PROJECT}" \
      --quiet >/dev/null || true
  done
else
  log "GCS bucket gs://${GCS_BUCKET} not found — skip object storage IAM (create the bucket first)"
fi

if [ -n "${GITHUB_REPO:-}" ]; then
  log "Configuring Workload Identity Federation for GitHub repo ${GITHUB_REPO}"
  POOL="starserve-github"
  PROVIDER="github"
  if ! gcloud iam workload-identity-pools describe "${POOL}" \
    --location=global --project="${GCP_PROJECT}" >/dev/null 2>&1; then
    gcloud iam workload-identity-pools create "${POOL}" \
      --location=global \
      --display-name="Star Serve GitHub" \
      --project="${GCP_PROJECT}"
  fi
  if ! gcloud iam workload-identity-pools providers describe "${PROVIDER}" \
    --workload-identity-pool="${POOL}" \
    --location=global --project="${GCP_PROJECT}" >/dev/null 2>&1; then
    gcloud iam workload-identity-pools providers create-oidc "${PROVIDER}" \
      --location=global \
      --workload-identity-pool="${POOL}" \
      --display-name="GitHub" \
      --issuer-uri="https://token.actions.githubusercontent.com" \
      --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
      --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
      --project="${GCP_PROJECT}"
  fi
  PROJECT_NUMBER="$(gcloud projects describe "${GCP_PROJECT}" --format='value(projectNumber)')"
  PRINCIPAL="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${GITHUB_REPO}"
  gcloud iam service-accounts add-iam-policy-binding \
    "starserve-deploy@${GCP_PROJECT}.iam.gserviceaccount.com" \
    --role="roles/iam.workloadIdentityUser" \
    --member="${PRINCIPAL}" \
    --project="${GCP_PROJECT}" \
    --quiet >/dev/null
  log "WIF ready. GitHub secrets:"
  log "  GCP_WIF_PROVIDER=projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"
  log "  GCP_DEPLOY_SA=starserve-deploy@${GCP_PROJECT}.iam.gserviceaccount.com"
fi

log "Bootstrap complete. Next: scripts/gcp/sync-secrets.sh staging && scripts/gcp/deploy.sh staging"

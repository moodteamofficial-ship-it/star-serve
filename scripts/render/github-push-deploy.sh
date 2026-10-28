#!/usr/bin/env bash
# Authenticate to GitHub, push star-serve, create/deploy starserve-api on Render.
#
# Auth (pick one):
#   1) echo 'ghp_...' > .github-token   (gitignored; repo scope on moodteamofficial-ship-it/star-serve)
#   2) gh auth login -h github.com -p https -w
#
#   export RENDER_API_KEY=rnd_...
#   ./scripts/render/github-push-deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=config.sh
source "${SCRIPT_DIR}/config.sh"
# shellcheck source=render-api.sh
source "${SCRIPT_DIR}/render-api.sh"

TOKEN_FILE="${ROOT}/.github-token"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/moodteamofficial-ship-it/star-serve}"

if ! gh auth status >/dev/null 2>&1; then
  if [ -f "${TOKEN_FILE}" ]; then
    render_log "GitHub login via .github-token"
    gh auth login --with-token < "${TOKEN_FILE}"
  else
    render_die "Not logged into GitHub. Run: gh auth login -h github.com -p https -w  OR create ${TOKEN_FILE}"
  fi
fi

gh auth setup-git
cd "${ROOT}"
git remote set-url origin "${GITHUB_REPO}.git"
render_log "Pushing main → ${GITHUB_REPO}"
git push -u origin main

export RENDER_GIT_REPO="${GITHUB_REPO}"
export RENDER_GIT_BRANCH="${RENDER_GIT_BRANCH:-main}"
"${SCRIPT_DIR}/deploy-render-all.sh" git

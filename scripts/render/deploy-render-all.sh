#!/usr/bin/env bash
# End-to-end: API on Render + dashboard wired to starserve-api.onrender.com
#
# Path 1 — Docker Hub (after: docker login)
#   export DOCKERHUB_USER=youruser
#   export RENDER_API_KEY=rnd_...
#   ./scripts/render/deploy-render-all.sh
#
# Path 2 — Git (after repo is on GitHub and connected in Render)
#   export RENDER_GIT_REPO=https://github.com/BirdviewInsurance/starserve-v1
#   ./scripts/render/deploy-render-all.sh git
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MODE="${1:-dockerhub}"
case "${MODE}" in
  git)
    exec "${SCRIPT_DIR}/deploy-git-stack.sh"
    ;;
  dockerhub)
    exec "${SCRIPT_DIR}/publish-and-deploy-api.sh"
    ;;
  *)
    echo "Usage: $0 [dockerhub|git]" >&2
    exit 2
    ;;
esac

#!/bin/bash
# Version Drift Detector — Monitor deployed environment staleness
#
# Detects when a deployed environment's reported commit SHA has fallen behind
# the main branch (indicates stale deployment), addressing issue #368.
#
# Usage:
#   ./scripts/check-version-drift.sh [DEPLOYED_URL] [TARGET_BRANCH]
#
# Environment variables (take precedence over args):
#   DEPLOYED_VERSION_URL  — Full URL to the /api/v1/version/ endpoint
#   TARGET_BRANCH         — Git branch to compare against (default: origin/main)
#
# Example:
#   DEPLOYED_VERSION_URL=https://app.example.com/api/v1/version/ \
#   ./scripts/check-version-drift.sh
#
#   # or with args:
#   ./scripts/check-version-drift.sh \
#     https://app.example.com/api/v1/version/ \
#     origin/production
#
# Exit codes:
#   0  — Deployed commit matches target (or is ancestor of target)
#   1  — Drift detected: deployed commit is behind or not in history
#   2  — Prerequisites missing (curl, jq, git, or network error)

set -euo pipefail

# Parse arguments
DEPLOYED_URL="${DEPLOYED_VERSION_URL:-${1:-}}"
TARGET_BRANCH="${TARGET_BRANCH:-${2:-origin/main}}"

# Validate prerequisites
if [[ -z "$DEPLOYED_URL" ]]; then
  echo "ERROR: DEPLOYED_VERSION_URL not provided."
  echo "Usage:"
  echo "  export DEPLOYED_VERSION_URL=https://your-app.com/api/v1/version/"
  echo "  ./scripts/check-version-drift.sh"
  exit 2
fi

if ! command -v curl &>/dev/null; then
  echo "ERROR: curl not found in PATH" >&2
  exit 2
fi

if ! command -v jq &>/dev/null; then
  echo "ERROR: jq not found in PATH" >&2
  exit 2
fi

if ! command -v git &>/dev/null; then
  echo "ERROR: git not found in PATH" >&2
  exit 2
fi

# Fetch deployed version metadata
echo "[check-version-drift] Fetching deployed version from: $DEPLOYED_URL"
version_response=$(curl -s -f "$DEPLOYED_URL" 2>&1) || {
  echo "ERROR: Failed to fetch version endpoint. Network error or endpoint unreachable." >&2
  echo "  URL: $DEPLOYED_URL" >&2
  exit 2
}

# Extract deployed commit_short
deployed_commit_short=$(echo "$version_response" | jq -r '.commit_short // "unknown"') || {
  echo "ERROR: Failed to parse version response as JSON." >&2
  echo "  Response: $version_response" >&2
  exit 2
}

deployed_app_version=$(echo "$version_response" | jq -r '.app_version // "unknown"') || {
  echo "WARNING: Failed to extract app_version from response."
  deployed_app_version="unknown"
}

if [[ "$deployed_commit_short" == "unknown" ]]; then
  echo "WARNING: Deployed commit is 'unknown' (not stamped at build)."
  echo "  This is expected for dev/docker-compose deployments."
  echo "  Skipping drift check."
  exit 0
fi

echo "[check-version-drift] Deployed: app_version=$deployed_app_version, commit_short=$deployed_commit_short"

# Fetch target branch HEAD
echo "[check-version-drift] Fetching $TARGET_BRANCH HEAD from git..."
target_sha=$(git rev-parse "$TARGET_BRANCH" 2>&1) || {
  echo "ERROR: Failed to resolve $TARGET_BRANCH (branch not found or not in local repo)." >&2
  exit 2
}

target_commit_short="${target_sha:0:7}"
echo "[check-version-drift] Target: $TARGET_BRANCH=$target_sha (short: $target_commit_short)"

# Compare commits
if [[ "$deployed_commit_short" == "$target_commit_short" ]]; then
  echo "[check-version-drift] SUCCESS: Deployed commit matches target branch (no drift detected)."
  exit 0
fi

# Check if deployed commit is an ancestor of target (acceptable if behind by a few commits)
if git merge-base --is-ancestor "$deployed_commit_short" "$target_sha" 2>/dev/null; then
  # Deployed commit is an ancestor; count commits behind
  commits_behind=$(git rev-list --count "$deployed_commit_short".."$target_sha") || {
    commits_behind="unknown"
  }
  echo "[check-version-drift] WARNING: Deployed commit is $commits_behind commit(s) behind $TARGET_BRANCH."
  echo "  Deployed: $deployed_commit_short"
  echo "  Target:   $target_commit_short"
  exit 1
fi

# Commit not in history at all
echo "[check-version-drift] CRITICAL: Deployed commit is NOT in the history of $TARGET_BRANCH."
echo "  This indicates a stale or orphaned deployment."
echo "  Deployed: $deployed_commit_short"
echo "  Target:   $target_commit_short ($TARGET_BRANCH)"
exit 1

#!/usr/bin/env bash
# deploy/bluepencil/fetch-layer.sh
#
# Fetch the Bluepencil browser layer from its PINNED upstream release and verify
# it before anything is published (plan D / D1.2, RB-D03, RB-D23).
#
# Why: the layer used to be committed into the repository
# (frontend/public/bluepencil/latest/*). Those bytes carried no provenance — the
# SPA served whatever a previous developer had copied in, and a layer update
# forced a frontend image rebuild. Now the bytes come from a release URL that is
# pinned in deploy/bluepencil/layer.lock.json alongside the expected SHA-256 of
# every asset, so:
#
#   * a fetch is reproducible (same lock -> same bytes, or a hard failure),
#   * a swapped/tampered release is refused instead of served, and
#   * a layer update is a lock bump plus this script — no image rebuild.
#
# Verification is fail-closed and happens BEFORE `--dest` is touched:
#   1. every asset is checked against the release's own SHA256SUMS,
#   2. and again against the hashes in the lock file,
#   3. the element must expose the host bridge the SPA relies on
#      (`getUser`, "global path") — this is the #988 guard against publishing a
#      layer build that silently cannot authenticate.
# Only then are the assets and the consolidated `latest.json` moved into place.
#
# Usage:
#   bash deploy/bluepencil/fetch-layer.sh [--dest DIR] [--lock FILE]
#
#   --dest DIR    where to materialise attach.js, bluepencil.element.min.js and
#                 latest.json (default: deploy/bluepencil/layer)
#   --lock FILE   the pin to verify against (default: deploy/bluepencil/layer.lock.json)
#   -h, --help    this text
#
# Relative paths are resolved against the current working directory.
#
# What writes into --dest:
#   * the Docker overlay (deploy/docker-compose.bluepencil.yml) bind-mounts that
#     directory read-only at /usr/share/nginx/html/bluepencil/latest,
#   * CI and `make bluepencil-layer` point it at frontend/public/bluepencil/latest,
#     which is what Vite serves in dev and what frontend/src/test/bluepencil-vendor.test.ts reads.
#
# Exit: 0 = verified and published, 1 = any deviation (nothing published),
#       2 = usage error.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DEST="$SCRIPT_DIR/layer"
LOCK="$SCRIPT_DIR/layer.lock.json"

#: Assets the SPA loads, in publish order. The element is the one whose hash the
#: `latest.json` manifest (and therefore the container healthcheck) pins.
element_name="bluepencil.element.min.js"
attach_name="attach.js"

usage() {
  # Everything between the shebang and the first executable line is the manual.
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dest)
      [ "$#" -ge 2 ] || die "--dest requires a directory argument (try --help)"
      DEST="$2"
      shift 2
      ;;
    --dest=*)
      DEST="${1#*=}"
      shift
      ;;
    --lock)
      [ "$#" -ge 2 ] || die "--lock requires a file argument (try --help)"
      LOCK="$2"
      shift 2
      ;;
    --lock=*)
      LOCK="${1#*=}"
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[ -n "$DEST" ] || die "--dest must not be empty"
[ -n "$LOCK" ] || die "--lock must not be empty"
[ -f "$LOCK" ] || die "lock file not found: $LOCK"

for tool in curl grep awk sed mv mkdir mktemp; do
  command -v "$tool" >/dev/null 2>&1 || die "required tool not found on PATH: $tool"
done

# GNU coreutils on Linux/CI; macOS ships shasum instead. Either prints the digest
# first, so the extraction is shared.
if command -v sha256sum >/dev/null 2>&1; then
  sha256_of() { sha256sum "$1" | awk '{ print tolower($1) }'; }
elif command -v shasum >/dev/null 2>&1; then
  sha256_of() { shasum -a 256 "$1" | awk '{ print tolower($1) }'; }
else
  die "neither sha256sum nor shasum found on PATH — cannot verify the download"
fi

# ---------------------------------------------------------------------------
# 1. Read the pin. The lock schema is fixed (written by hand, bumped per
#    release), so key extraction is textual instead of pulling in a JSON
#    toolchain; a missing key is a hard failure, never an empty default.
# ---------------------------------------------------------------------------
json_string() {
  # $1 = key, $2 = file  -> first "value" for that key, empty when absent.
  grep -o "\"$1\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$2" \
    | head -n1 \
    | sed -e 's/^"[^"]*"[[:space:]]*:[[:space:]]*"//' -e 's/"$//'
}

lock_version="$(json_string version "$LOCK")"
lock_release="$(json_string release "$LOCK")"
lock_attach_sha="$(json_string 'attach\.js' "$LOCK")"
lock_element_sha="$(json_string "$(printf '%s' "$element_name" | sed 's/\./\\./g')" "$LOCK")"

[ -n "$lock_version" ] || die "lock is malformed: no \"version\" in $LOCK"
[ -n "$lock_release" ] || die "lock is malformed: no \"release\" in $LOCK"
[ -n "$lock_attach_sha" ] || die "lock is malformed: no assets[\"$attach_name\"] in $LOCK"
[ -n "$lock_element_sha" ] || die "lock is malformed: no assets[\"$element_name\"] in $LOCK"

# Normalise the release base so appending a file name is unambiguous.
release_base="${lock_release%/}/"

# ---------------------------------------------------------------------------
# 2. Stage next to --dest (same filesystem, so the final publish is a rename and
#    a failed run leaves the destination exactly as it was). The parent is
#    created here only because mktemp needs it; no asset is written outside the
#    staging directory until every check below has passed.
# ---------------------------------------------------------------------------
dest_parent="$(dirname "$DEST")"
mkdir -p "$dest_parent"
stage="$(mktemp -d "$dest_parent/.bluepencil-layer.XXXXXX")"
cleanup() { rm -rf "$stage"; }
trap cleanup EXIT

fetch() {
  # $1 = file name -> downloads into the staging directory.
  local url="${release_base}$1"
  if ! curl -fsSL --retry 3 --retry-delay 2 -o "$stage/$1" "$url"; then
    die "download failed: $url (release v$lock_version unreachable or asset missing)"
  fi
}

printf 'fetching bluepencil v%s from %s\n' "$lock_version" "$release_base"
fetch SHA256SUMS
fetch "$attach_name"
fetch "$element_name"

# ---------------------------------------------------------------------------
# 3a. Verify against the release's own SHA256SUMS. The line format is
#     "<sha>  <name>" (or "<sha> *<name>" for binary mode).
# ---------------------------------------------------------------------------
sums_for() {
  # $1 = file name -> the SHA-256 the release advertises for it, empty if absent.
  awk -v file="$1" '{ name = $2; sub(/^\*/, "", name) } name == file { print tolower($1); exit }' \
    "$stage/SHA256SUMS"
}

actual_sha() {
  sha256_of "$stage/$1"
}

expected_attach_sums="$(sums_for "$attach_name")"
expected_element_sums="$(sums_for "$element_name")"

[ -n "$expected_attach_sums" ] || die "SHA256SUMS of v$lock_version lists no $attach_name"
[ -n "$expected_element_sums" ] || die "SHA256SUMS of v$lock_version lists no $element_name"

actual_attach_sha="$(actual_sha "$attach_name")"
actual_element_sha="$(actual_sha "$element_name")"

if [ "$actual_attach_sha" != "$expected_attach_sums" ]; then
  die "$attach_name does not match the release SHA256SUMS (expected $expected_attach_sums, got $actual_attach_sha)"
fi
if [ "$actual_element_sha" != "$expected_element_sums" ]; then
  die "$element_name does not match the release SHA256SUMS (expected $expected_element_sums, got $actual_element_sha)"
fi

# ---------------------------------------------------------------------------
# 3b. Verify against the pin. A release that is internally consistent but not
#     the one this checkout expects is still refused — that is what makes the
#     lock (not the upstream server) the source of truth.
# ---------------------------------------------------------------------------
lock_attach_sha="$(printf '%s' "$lock_attach_sha" | tr '[:upper:]' '[:lower:]')"
lock_element_sha="$(printf '%s' "$lock_element_sha" | tr '[:upper:]' '[:lower:]')"

if [ "$actual_attach_sha" != "$lock_attach_sha" ]; then
  die "$attach_name does not match the lock (lock $lock_attach_sha, release $actual_attach_sha); bump $LOCK only after auditing the new release"
fi
if [ "$actual_element_sha" != "$lock_element_sha" ]; then
  die "$element_name does not match the lock (lock $lock_element_sha, release $actual_element_sha); bump $LOCK only after auditing the new release"
fi

# ---------------------------------------------------------------------------
# 3c. #988 guard: a layer that cannot resolve the host bridge silently breaks
#     the review workflow, so refuse it here instead of after deploy.
# ---------------------------------------------------------------------------
if ! grep -q "getUser" "$stage/$element_name"; then
  die "$element_name exposes no getUser bridge (#988 guard) — the SPA could not authenticate the layer"
fi
if ! grep -q "global path" "$stage/$element_name"; then
  die "$element_name has no \"global path\" marker (#988 guard) — refusing an unrecognised layer build"
fi

# ---------------------------------------------------------------------------
# 4. Publish. Moved one file at a time (each rename is atomic); latest.json goes
#    last so a reader never sees a manifest that points at absent bytes. The
#    container healthcheck re-verifies exactly that pairing at start.
# ---------------------------------------------------------------------------
mkdir -p "$DEST"
mv "$stage/$attach_name" "$DEST/$attach_name"
mv "$stage/$element_name" "$DEST/$element_name"

cat >"$stage/latest.json" <<EOF
{
  "version": "$lock_version",
  "element": "$element_name",
  "sha256": "$actual_element_sha"
}
EOF
mv "$stage/latest.json" "$DEST/latest.json"

printf 'OK: bluepencil v%s verified and published to %s\n' "$lock_version" "$DEST"
printf '    %s %s\n' "$attach_name" "$actual_attach_sha"
printf '    %s %s\n' "$element_name" "$actual_element_sha"

#!/usr/bin/env bash
# ReqogniLoom — one-step environment bootstrap (#792 points 7 and 12, plan D3.2).
#
# WHAT IT DOES
#   1. Creates the target env file from `.env.example` when it does not exist.
#   2. Generates two kinds of value, and ONLY these two:
#        a) every value that still carries the template's `CHANGE-ME` marker;
#        b) the keys listed in `EMPTY_KEYS` when they exist with an EMPTY (or
#           whitespace-only) value — `API_KEY_PEPPER` (plan P1.3) and
#           `SYSTEM_ADMIN_PASSWORD` (plan P1.1). Both ship empty in the
#           template, because a literal placeholder would be worse: for the
#           pepper the startup check treats empty as "must be generated", and
#           for the admin password a NON-empty trivial value aborts `migrate`
#           (fail-closed) instead of just meaning "no admin account".
#      Every other value a human already set is left untouched (idempotent).
#   3. Locks the file down to mode 600 and prints the NAMES of the generated
#      keys — never their values.
#   4. With `--check-ports`: refuses to continue when BACKEND_PORT (default
#      8001) or FRONTEND_PORT (default 5173) is already bound on 127.0.0.1,
#      which is the failure mode #792 point 12 describes (two stacks fighting
#      over the same host port).
#
# WHAT IT DELIBERATELY DOES NOT DO
#   No database initialisation. The app role, pgvector and the schema are
#   created by the one-shot `migrate` service (migration 0048 + the migrations
#   themselves), so a `setup.sh` that also ran `psql` would duplicate — and
#   could contradict — the migration path (#792 point 7 is obsolete there).
#
#   No generation of the OPTIONAL secrets (`REDIS_PASSWORD`, the Honcho webhook
#   key, `IMPORT_FINGERPRINT_SECRET`, `QDRANT_API_KEY`, ...). They are
#   legitimately empty — an empty Redis password means "no requirepass", an
#   empty webhook key means "receiver disabled" — so inventing values here would
#   change documented behaviour instead of hardening it. Only values the
#   application cannot run correctly without are generated.
#
# SECRET HYGIENE (QR-S03, plan D2.6)
#   An existing env file is only ever backed up OUTSIDE the repository, under
#   ${XDG_STATE_HOME:-$HOME/.local/state}/reqogniloom/env-backups/<ts>.env with
#   mode 600. No `.env.bak*` is ever written next to the file: the 2026-10-21
#   incident was exactly a secret-bearing backup sitting untracked in the repo.
#   A target path inside the repository must be git-ignored; otherwise the
#   script stops with exit 3 rather than leaving secrets one `git add -A` away.
#
# Usage: scripts/setup.sh [--env-file PATH] [--check-ports]
# Exit:  0 ok · 2 a port is in use · 3 target env file is not git-ignored
set -euo pipefail

umask 077

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null \
  || printf '%s' "$(cd -- "$SCRIPT_DIR/.." && pwd)")
TEMPLATE="$REPO_ROOT/.env.example"
ENV_FILE="$REPO_ROOT/.env"
CHECK_PORTS=0

# The only keys this script generates from a CHANGE-ME placeholder.
# Everything else is a human decision. `SYSTEM_ADMIN_PASSWORD` is also in
# `EMPTY_KEYS` below: an `.env` copied from an older template still carries
# `CHANGE-ME-strong-admin-password`, and that value must be replaced (it would
# otherwise abort `migrate` fail-closed) — keeping it in both lists covers both
# template generations.
REPLACE_KEYS=(
  SECRET_KEY
  AUTH_JWT_SECRET
  DB_PASSWORD
  DB_APP_PASSWORD
  SYSTEM_ADMIN_PASSWORD
  FIELD_ENCRYPTION_KEY
)

# Keys generated when they are present with an EMPTY value. Two of them ship
# empty in `.env.example` on purpose:
#   * `API_KEY_PEPPER` (plan P1.3) — the production startup check
#     `reqogniloom.E001` treats "empty" as "must be generated", and a CHANGE-ME
#     literal would only add a second, weaker failure mode.
#   * `SYSTEM_ADMIN_PASSWORD` (plan P1.1) — empty means "no admin account is
#     provisioned", which is what a plain `cp .env.example .env` must do: a
#     NON-empty placeholder would make `migrate` abort fail-closed and break the
#     documented quickstart. The recommended path (this script) still creates
#     the admin by filling the key here.
# A key that is ABSENT from the file is left absent — this script fills
# placeholders, it does not add settings.
EMPTY_KEYS=(
  API_KEY_PEPPER
  SYSTEM_ADMIN_PASSWORD
)

usage() {
  cat <<'EOF'
Usage: bash scripts/setup.sh [--env-file PATH] [--check-ports]

  --env-file PATH   Target env file (default: <repo>/.env). Created from
                    .env.example when absent.
  --check-ports     After writing, fail with exit 2 if BACKEND_PORT (default
                    8001) or FRONTEND_PORT (default 5173) is already in use.

Fills every CHANGE-ME placeholder and every empty required value
(API_KEY_PEPPER, SYSTEM_ADMIN_PASSWORD); every other existing value is
kept as-is.
EOF
}

die() {
  echo "setup: $*" >&2
  exit 1
}

while [ $# -gt 0 ]; do
  case "$1" in
    --env-file)
      [ $# -ge 2 ] || die "--env-file needs a path"
      ENV_FILE=$2
      shift 2
      ;;
    --env-file=*)
      ENV_FILE=${1#*=}
      [ -n "$ENV_FILE" ] || die "--env-file needs a path"
      shift
      ;;
    --check-ports)
      CHECK_PORTS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "setup: unknown argument: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

# Absolute, non-symlink-resolving path — containment is a prefix question and
# resolving symlinks could move the answer outside the checkout.
abspath() {
  case "$1" in
    /*) printf '%s' "$1" ;;
    *) printf '%s/%s' "$PWD" "$1" ;;
  esac
}

# Last uncommented occurrence wins, matching Compose's own .env precedence.
env_value() {
  local file=$1 key=$2 line
  line=$(grep -E "^${key}=" "$file" 2>/dev/null | tail -n 1 || true)
  [ -n "$line" ] || return 0
  printf '%s' "${line#*=}" | tr -d '\r'
}

gen_hex50() {
  openssl rand -hex 50
}

gen_password() {
  # 32 random bytes without the characters that need shell quoting in .env.
  openssl rand -base64 32 | tr -d '/+='
}

gen_fernet() {
  # Fernet wants urlsafe-base64 of exactly 32 bytes: base64 -> urlsafe alphabet.
  openssl rand -base64 32 | tr '+/' '-_'
}

new_secret() {
  case "$1" in
    SECRET_KEY|AUTH_JWT_SECRET) gen_hex50 ;;
    FIELD_ENCRYPTION_KEY) gen_fernet ;;
    # HMAC pepper for the API-key hashes. Hex rather than gen_password: the
    # latter strips every '+', '/' and '=' from a base64 draw, which cannot
    # guarantee the 32-character floor that the `reqogniloom.E002` check
    # enforces on every draw.
    API_KEY_PEPPER) gen_hex50 ;;
    *) gen_password ;;
  esac
}

backup_env() {
  local src=$1 backup_dir timestamp backup
  backup_dir="${XDG_STATE_HOME:-$HOME/.local/state}/reqogniloom/env-backups"
  timestamp=$(date -u +%Y%m%dT%H%M%SZ)
  mkdir -p -- "$backup_dir"
  backup="$backup_dir/${timestamp}-$$.env"
  cp -- "$src" "$backup"
  chmod 600 -- "$backup"
  echo "backup: $backup (mode 600, outside the repository)"
}

[ -d "$REPO_ROOT" ] || die "repository root not found"

CREATED=0
if [ ! -f "$ENV_FILE" ]; then
  [ -f "$TEMPLATE" ] || die "template not found: $TEMPLATE"
  mkdir -p -- "$(dirname -- "$ENV_FILE")"
  cp -- "$TEMPLATE" "$ENV_FILE"
  CREATED=1
  echo "created: $ENV_FILE (from .env.example)"
fi

PENDING=()
add_pending() {
  # A key can qualify through both lists (see REPLACE_KEYS), and an env file can
  # contain more than one active line for it. Collect it once, so the value is
  # generated once and reported once.
  local candidate=$1 existing
  if [ ${#PENDING[@]} -gt 0 ]; then
    for existing in "${PENDING[@]}"; do
      [ "$existing" = "$candidate" ] && return 0
    done
  fi
  PENDING+=("$candidate")
}
for key in "${REPLACE_KEYS[@]}"; do
  if grep -qE "^${key}=CHANGE-ME" "$ENV_FILE"; then
    add_pending "$key"
  fi
done
# Empty (not missing) values: `KEY=` with nothing after it, or only whitespace.
for key in "${EMPTY_KEYS[@]}"; do
  if grep -qE "^${key}=[[:space:]]*\$" "$ENV_FILE"; then
    add_pending "$key"
  fi
done

if [ ${#PENDING[@]} -gt 0 ]; then
  declare -A NEW=()
  for key in "${PENDING[@]}"; do
    NEW["$key"]=$(new_secret "$key")
  done

  # Only a file that already existed is worth backing up: a file this run just
  # copied from the tracked template has no secret to protect yet.
  if [ "$CREATED" -eq 0 ]; then
    backup_env "$ENV_FILE"
  fi

  tmp=$(mktemp)
  trap 'rm -f -- "$tmp"' EXIT
  while IFS= read -r line || [ -n "$line" ]; do
    for key in "${PENDING[@]}"; do
      # This branch must accept exactly what the detection above accepted:
      # a CHANGE-ME placeholder, a truly empty `KEY=`, and a whitespace-only
      # `KEY=   `. The previous `"${key}="` case pattern matched only the empty
      # form, so a whitespace-only line was reported as "generated" while being
      # left untouched — the value stayed blank and the reason was invisible.
      if [[ $line =~ ^(${key})=(CHANGE-ME.*|[[:space:]]*)$ ]]; then
        line="${key}=${NEW[$key]}"
      fi
    done
    printf '%s\n' "$line" >>"$tmp"
  done <"$ENV_FILE"
  cat -- "$tmp" >"$ENV_FILE"
  rm -f -- "$tmp"
  trap - EXIT

  for key in "${PENDING[@]}"; do
    echo "generated: $key"
  done
else
  echo "unchanged: nothing to generate in $ENV_FILE"
fi

chmod 600 -- "$ENV_FILE"

# A secret file inside the checkout is only acceptable while git ignores it.
ENV_ABS=$(abspath "$ENV_FILE")
case "$ENV_ABS" in
  "$REPO_ROOT"/*)
    if ! git -C "$REPO_ROOT" check-ignore -q -- "$ENV_ABS"; then
      echo "setup: refusing to keep $ENV_ABS inside the repository — it is not git-ignored" >&2
      echo "setup: add an ignore rule (see .gitignore) or pass --env-file outside the checkout" >&2
      exit 3
    fi
    ;;
esac

if [ "$CHECK_PORTS" -eq 1 ]; then
  BACKEND_PORT=$(env_value "$ENV_FILE" BACKEND_PORT)
  FRONTEND_PORT=$(env_value "$ENV_FILE" FRONTEND_PORT)
  BACKEND_PORT=${BACKEND_PORT:-8001}
  FRONTEND_PORT=${FRONTEND_PORT:-5173}

  for spec in "BACKEND_PORT:$BACKEND_PORT" "FRONTEND_PORT:$FRONTEND_PORT"; do
    name=${spec%%:*}
    port=${spec#*:}
    case "$port" in
      ''|*[!0-9]*)
        echo "setup: $name=$port is not a valid TCP port" >&2
        exit 3
        ;;
    esac
    # /dev/tcp is a bash built-in: a failed connect is non-zero, no packets are
    # written, and no external tool (ss/netstat) has to be present.
    if (exec 3>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
      echo "Port $port is already in use — set BACKEND_PORT/FRONTEND_PORT in $ENV_FILE" >&2
      exit 2
    fi
  done
  echo "ports: $BACKEND_PORT (backend) and $FRONTEND_PORT (frontend) are free"
fi

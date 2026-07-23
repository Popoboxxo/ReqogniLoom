#!/bin/bash

###############################################################################
# PostgreSQL Backup Script for ReqogniLoom
#
# Description:
#   Backup the PostgreSQL database using pg_dump via Docker Compose.
#   - Uses docker-compose.backup.yml service definition
#   - Saves dumps to ./backups/ directory
#   - Implements 7-day retention policy (older backups deleted)
#   - Supports custom database credentials via environment variables
#
# Usage:
#   ./scripts/backup.sh              # Run immediate backup
#   ./scripts/backup.sh --cleanup    # Cleanup old backups (7+ days)
#   ./scripts/backup.sh --list       # List existing backups
#
# Environment Variables:
#   DB_USER      - PostgreSQL username (default: reqogniloom)
#   DB_PASSWORD  - PostgreSQL password (default: reqogniloom)
#   DB_NAME      - Database name (default: reqogniloom)
#   BACKUP_RETENTION_DAYS - Days to keep backups (default: 7)
#
# Requirements:
#   - docker/docker-compose installed
#   - postgres service running (docker-compose.yml)
#   - Write permission to ./backups/ directory
#
# Author: ReqogniLoom DevOps
# Last Updated: 2026-07-14
###############################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUPS_DIR="${PROJECT_ROOT}/backups"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

###############################################################################
# Helper Functions
###############################################################################

log_info() {
  echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $*" >&2
}

check_prerequisites() {
  if ! command -v docker &> /dev/null; then
    log_error "docker is not installed or not in PATH"
    exit 1
  fi

  if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    log_error "docker-compose is not installed or not in PATH"
    exit 1
  fi

  if [ ! -f "${PROJECT_ROOT}/docker-compose.yml" ]; then
    log_error "docker-compose.yml not found at ${PROJECT_ROOT}"
    exit 1
  fi

  if [ ! -f "${PROJECT_ROOT}/docker-compose.backup.yml" ]; then
    log_error "docker-compose.backup.yml not found at ${PROJECT_ROOT}"
    exit 1
  fi
}

create_backups_directory() {
  if [ ! -d "$BACKUPS_DIR" ]; then
    log_info "Creating backups directory: $BACKUPS_DIR"
    mkdir -p "$BACKUPS_DIR"
  fi
}

run_backup() {
  log_info "Starting PostgreSQL backup..."

  cd "$PROJECT_ROOT"

  if docker-compose --version &> /dev/null; then
    docker-compose -f docker-compose.yml -f docker-compose.backup.yml run --rm backup
  else
    docker compose -f docker-compose.yml -f docker-compose.backup.yml run --rm backup
  fi

  if [ $? -eq 0 ]; then
    log_info "Backup completed successfully"
  else
    log_error "Backup failed"
    exit 1
  fi
}

list_backups() {
  if [ ! -d "$BACKUPS_DIR" ]; then
    log_warn "Backups directory does not exist: $BACKUPS_DIR"
    return
  fi

  log_info "Available backups:"
  if [ -z "$(ls -A "$BACKUPS_DIR")" ]; then
    echo "  (no backups found)"
  else
    ls -lh "$BACKUPS_DIR" | tail -n +2 | awk '{printf "  %s  %s  %s\n", $9, $5, $6" "$7" "$8}'
  fi
}

cleanup_old_backups() {
  if [ ! -d "$BACKUPS_DIR" ]; then
    log_warn "Backups directory does not exist: $BACKUPS_DIR"
    return
  fi

  log_info "Cleaning up backups older than $RETENTION_DAYS days..."

  local count=0
  while IFS= read -r -d '' file; do
    log_info "Deleting old backup: $(basename "$file")"
    rm -f "$file"
    ((count++)) || true
  done < <(find "$BACKUPS_DIR" -maxdepth 1 -type f -mtime +${RETENTION_DAYS} -print0)

  if [ $count -eq 0 ]; then
    log_info "No backups older than $RETENTION_DAYS days found"
  else
    log_info "Deleted $count old backup(s)"
  fi
}

###############################################################################
# Main Script
###############################################################################

main() {
  check_prerequisites
  create_backups_directory

  case "${1:-}" in
    --cleanup)
      cleanup_old_backups
      ;;
    --list)
      list_backups
      ;;
    --help|-h)
      echo "PostgreSQL Backup Script for ReqFlow"
      echo ""
      echo "Usage: $0 [OPTION]"
      echo ""
      echo "Options:"
      echo "  (no args)     Run immediate backup"
      echo "  --cleanup     Delete backups older than $RETENTION_DAYS days"
      echo "  --list        List existing backups"
      echo "  --help        Show this help message"
      echo ""
      echo "Environment Variables:"
      echo "  DB_USER              PostgreSQL username (default: reqogniloom)"
      echo "  DB_PASSWORD          PostgreSQL password (default: reqogniloom)"
      echo "  DB_NAME              Database name (default: reqogniloom)"
      echo "  BACKUP_RETENTION_DAYS Days to keep backups (default: 7)"
      ;;
    *)
      run_backup
      list_backups
      ;;
  esac
}

main "$@"

#!/bin/bash

###############################################################################
# PostgreSQL Restore Script for ReqogniLoom
#
# Description:
#   Restore a PostgreSQL database from a backup dump file created by backup.sh.
#   - Supports .dump (custom format) and .sql (plain text) files
#   - Validates backup file exists before restore
#   - Requires confirmation before overwriting database
#   - Supports custom database credentials via environment variables
#
# Usage:
#   ./scripts/restore.sh <backup_file>              # Restore from backup
#   ./scripts/restore.sh --list                     # List available backups
#   ./scripts/restore.sh --latest                   # Restore from latest backup
#   ./scripts/restore.sh --help                     # Show help
#
# Examples:
#   ./scripts/restore.sh backups/reqogniloom_20260714_143022.dump
#   ./scripts/restore.sh --latest
#   ./scripts/restore.sh --list
#
# Environment Variables:
#   DB_USER      - PostgreSQL username (default: reqogniloom)
#   DB_PASSWORD  - PostgreSQL password (default: reqogniloom)
#   DB_NAME      - Database name (default: reqogniloom)
#   RESTORE_CONFIRM - Skip confirmation if set to "yes" (default: no)
#
# Requirements:
#   - docker/docker-compose installed
#   - postgres service running (docker-compose.yml)
#   - Valid backup file in .dump or .sql format
#   - Database connectivity
#
# WARNING:
#   This operation OVERWRITES the current database.
#   Always verify you have the correct backup file before proceeding.
#
# Author: ReqogniLoom DevOps
# Last Updated: 2026-07-14
###############################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUPS_DIR="${PROJECT_ROOT}/backups"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_debug() {
  echo -e "${BLUE}[DEBUG]${NC} $*"
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
}

list_backups() {
  if [ ! -d "$BACKUPS_DIR" ]; then
    log_warn "Backups directory does not exist: $BACKUPS_DIR"
    return
  fi

  log_info "Available backups:"
  if [ -z "$(ls -A "$BACKUPS_DIR" 2>/dev/null)" ]; then
    echo "  (no backups found)"
  else
    ls -lh "$BACKUPS_DIR" 2>/dev/null | tail -n +2 | awk '{printf "  %s  %s  %s %s %s\n", $9, $5, $6, $7, $8}' || echo "  (no backups found)"
  fi
}

get_latest_backup() {
  if [ ! -d "$BACKUPS_DIR" ]; then
    log_error "Backups directory does not exist: $BACKUPS_DIR"
    exit 1
  fi

  local latest_backup
  latest_backup=$(ls -t "$BACKUPS_DIR"/*.dump "$BACKUPS_DIR"/*.sql 2>/dev/null | head -n1)

  if [ -z "$latest_backup" ]; then
    log_error "No backup files found in $BACKUPS_DIR"
    exit 1
  fi

  echo "$latest_backup"
}

validate_backup_file() {
  local backup_file="$1"

  if [ ! -f "$backup_file" ]; then
    log_error "Backup file not found: $backup_file"
    exit 1
  fi

  local file_size
  file_size=$(stat -f%z "$backup_file" 2>/dev/null || stat -c%s "$backup_file" 2>/dev/null || echo "0")

  if [ "$file_size" -lt 1024 ]; then
    log_error "Backup file is suspiciously small ($file_size bytes). Aborting restore."
    exit 1
  fi

  log_info "Backup file validated: $backup_file ($(numfmt --to=iec $file_size 2>/dev/null || echo "$file_size bytes"))"
}

confirm_restore() {
  local backup_file="$1"

  if [ "${RESTORE_CONFIRM:-no}" == "yes" ]; then
    log_warn "RESTORE_CONFIRM=yes: Skipping confirmation prompt"
    return 0
  fi

  echo ""
  log_warn "WARNING: This will OVERWRITE the current database!"
  echo -e "  Backup file: ${BLUE}$backup_file${NC}"
  echo -e "  Database: ${BLUE}${DB_NAME:-reqogniloom}${NC}"
  echo ""

  read -p "Type 'restore' to confirm, or press Enter to cancel: " -r confirmation

  if [ "$confirmation" != "restore" ]; then
    log_info "Restore cancelled by user"
    exit 0
  fi

  log_warn "Restore confirmed - proceeding with database restore"
}

run_restore() {
  local backup_file="$1"
  local file_extension="${backup_file##*.}"

  log_info "Preparing to restore from: $backup_file"
  log_info "Restore method: $file_extension format"

  cd "$PROJECT_ROOT"

  # Create a temporary restore script based on file format
  local restore_command

  if [ "$file_extension" = "dump" ]; then
    # Custom format (pg_restore)
    restore_command="pg_restore -h postgres -U \${DB_USER:-reqogniloom} -d \${DB_NAME:-reqogniloom} --clean --if-exists -v /tmp/backup.dump"
  elif [ "$file_extension" = "sql" ]; then
    # Plain text SQL format (psql)
    restore_command="psql -h postgres -U \${DB_USER:-reqogniloom} -d \${DB_NAME:-reqogniloom} -f /tmp/backup.sql"
  else
    log_error "Unsupported backup file format: $file_extension (expected .dump or .sql)"
    exit 1
  fi

  log_info "Starting database restore... This may take a few minutes."

  # Copy backup file to temp and run restore via postgres container
  if docker-compose --version &> /dev/null; then
    docker-compose -f docker-compose.yml exec -T postgres bash -c "
      export PGPASSWORD=\${DB_PASSWORD:-reqogniloom}
      $restore_command
    " < "$backup_file" || {
      log_error "Restore operation failed"
      exit 1
    }
  else
    docker compose -f docker-compose.yml exec -T postgres bash -c "
      export PGPASSWORD=\${DB_PASSWORD:-reqogniloom}
      $restore_command
    " < "$backup_file" || {
      log_error "Restore operation failed"
      exit 1
    }
  fi

  log_info "Database restore completed successfully"
}

###############################################################################
# Main Script
###############################################################################

main() {
  check_prerequisites

  case "${1:-}" in
    --list)
      list_backups
      ;;
    --latest)
      log_info "Finding latest backup..."
      latest=$(get_latest_backup)
      log_info "Latest backup: $latest"
      validate_backup_file "$latest"
      confirm_restore "$latest"
      run_restore "$latest"
      ;;
    --help|-h)
      echo "PostgreSQL Restore Script for ReqFlow"
      echo ""
      echo "Usage: $0 [OPTION] [backup_file]"
      echo ""
      echo "Options:"
      echo "  <backup_file> Restore from specified backup file"
      echo "  --latest      Restore from most recent backup"
      echo "  --list        List available backups"
      echo "  --help        Show this help message"
      echo ""
      echo "Environment Variables:"
      echo "  DB_USER          PostgreSQL username (default: reqogniloom)"
      echo "  DB_PASSWORD      PostgreSQL password (default: reqogniloom)"
      echo "  DB_NAME          Database name (default: reqogniloom)"
      echo "  RESTORE_CONFIRM  Skip confirmation if set to 'yes' (default: no)"
      echo ""
      echo "Examples:"
      echo "  $0 backups/reqogniloom_20260714_143022.dump"
      echo "  $0 --latest"
      echo "  RESTORE_CONFIRM=yes $0 --latest"
      ;;
    "")
      log_error "No backup file specified"
      echo "Usage: $0 <backup_file> | --latest | --list | --help"
      exit 1
      ;;
    *)
      if [ -f "$1" ]; then
        validate_backup_file "$1"
        confirm_restore "$1"
        run_restore "$1"
      else
        log_error "Backup file not found: $1"
        exit 1
      fi
      ;;
  esac
}

main "$@"

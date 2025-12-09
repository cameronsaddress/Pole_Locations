#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_SCRIPT="${SCRIPT_DIR}/start_host.sh"
if [[ ! -f "${HOST_SCRIPT}" ]]; then
  echo "start_host.sh not found" >&2
  exit 1
fi

exec /bin/bash "${HOST_SCRIPT}"

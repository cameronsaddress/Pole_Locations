#!/usr/bin/env bash
set -euo pipefail

source /opt/conda/etc/profile.d/conda.sh || true

if [ -d ".venv-gpu" ]; then
  source .venv-gpu/bin/activate
fi

export PATH="/home/canderson/node-v20.18.1-linux-arm64/bin:$PATH"
export RUN_PIPELINE=1
./start.sh

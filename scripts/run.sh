#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -n "${BROCHURE_PYTHON:-}" ]]; then
  runtime="$BROCHURE_PYTHON"
elif [[ -x .venv/bin/python ]]; then
  runtime=.venv/bin/python
elif [[ -x /home/seanhan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 ]]; then
  runtime=/home/seanhan/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3
else
  runtime=python3
fi
exec "$runtime" -m brochure.server "$@"

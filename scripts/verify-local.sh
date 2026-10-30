#!/usr/bin/env bash
# Repeatable local candidate gate. This does not certify a deployed service.
set -euo pipefail
cd "$(dirname "$0")/.."
agentos_python="${AGENTOS_PYTHON:-.venv/bin/python}"
"$agentos_python" --version
"$agentos_python" -m pytest backend/tests -q
"$agentos_python" -m pip check
npm --prefix frontend run lint -- --max-warnings=0
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run typecheck
if [[ "${AGENTOS_BROWSER_TESTS:-1}" == "1" ]]; then
  npm --prefix frontend run test:e2e:production -- --reporter=line
else
  echo 'Browser acceptance skipped: release gate remains incomplete.'
fi

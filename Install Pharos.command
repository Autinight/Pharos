#!/bin/bash
# Native macOS installer entry point. No research jobs are started.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$(uname -s)" != Darwin ]; then
  echo 'This entry point is for macOS. On Linux run: bash scripts/bootstrap.sh' >&2
  exit 1
fi
printf 'Installing Pharos into: %s/runtime\n' "$ROOT"
printf '%s\n' 'This downloads dependencies and creates a pharos link in ~/.local/bin.' \
  'Keep this folder in place. No research or model request is started.'
bash "$ROOT/scripts/bootstrap.sh"
printf '\n%s\n' 'Installation complete. Configure your backend separately; see docs/macos.md.'

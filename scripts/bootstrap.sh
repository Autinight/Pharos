#!/usr/bin/env bash
# Install the Pharos runtime on Linux or macOS. No model/research job is started.
# Usage: bash scripts/bootstrap.sh [--print-plan]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PHAROS_ROOT="$(cd "$HERE/.." && pwd)"
. "$HERE/platform.sh"
RT="$PHAROS_ROOT/runtime"
NODE_VERSION="${NODE_VERSION:-v22.14.0}"
CODEX_NPM_VERSION="${PHAROS_CODEX_SOURCE_VERSION:-0.163.0}"
TARBALL="$(pharos_node_archive "$NODE_VERSION")"
PYBASE="$(pharos_find_python)"
HOST="$(uname -s)"
log(){ printf '[bootstrap] %s\n' "$*"; }
case "${1:-}" in
  --print-plan)
    printf 'platform=%s\nnode_archive=%s\npython=%s\nruntime=%s\ncodex_npm_version=%s\n' \
      "$HOST" "$TARBALL" "$PYBASE" "$RT" "$CODEX_NPM_VERSION"
    exit 0 ;;
  '') ;;
  *) echo 'Usage: bash scripts/bootstrap.sh [--print-plan]' >&2; exit 2 ;;
esac
mkdir -p "$RT/logs"

# Keep installation IO/CPU polite. ionice is optional and Linux-specific.
NICE=(nice -n 19)
if command -v ionice >/dev/null 2>&1; then NICE=(ionice -c3 nice -n 19); fi

NODE_DIR="$RT/node22"
if [ -x "$NODE_DIR/bin/node" ] && "$NODE_DIR/bin/node" --version >/dev/null 2>&1; then
  log "node present: $("$NODE_DIR/bin/node" --version)"
else
  log "installing Node $NODE_VERSION ($HOST) -> $NODE_DIR"
  "${NICE[@]}" curl -fSL --retry 2 "https://nodejs.org/dist/$NODE_VERSION/$TARBALL" -o "$RT/$TARBALL"
  curl -fsSL --retry 2 "https://nodejs.org/dist/$NODE_VERSION/SHASUMS256.txt" -o "$RT/node-shasums.txt"
  "$PYBASE" - "$RT/$TARBALL" "$RT/node-shasums.txt" <<'PY'
import hashlib, pathlib, sys
archive, checksums = map(pathlib.Path, sys.argv[1:])
expected = next((line.split()[0] for line in checksums.read_text().splitlines()
                 if len(line.split()) == 2 and line.split()[1] == archive.name), None)
with archive.open('rb') as stream:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(chunk)
if not expected or digest.hexdigest() != expected:
    raise SystemExit('Node checksum mismatch or missing checksum; refusing to extract')
PY
  mkdir -p "$NODE_DIR"
  tar -xf "$RT/$TARBALL" -C "$NODE_DIR" --strip-components=1
  "$NODE_DIR/bin/node" --version
  rm -f "$RT/$TARBALL" "$RT/node-shasums.txt"
fi
export PATH="$NODE_DIR/bin:$PATH"

VENV="$RT/venv"
export PIP_DISABLE_PIP_VERSION_CHECK=1
DEPS='import mcp,fastapi,uvicorn,pydantic,openai,pytest,markdown_it,mdit_py_plugins; from pypdf import PdfReader; import sys; assert sys.version_info >= (3,10)'
if [ "$HOST" = Darwin ]; then DEPS="$DEPS; import psutil"; fi
if "$VENV/bin/python" -c "$DEPS" 2>/dev/null; then
  log 'venv present + healthy'
else
  # The runtime venv is generated, never a user's unrelated environment.
  if [ -e "$VENV" ]; then log 'rebuilding generated runtime/venv'; rm -rf "$VENV"; fi
  "$PYBASE" -m venv "$VENV"
  "${NICE[@]}" "$VENV/bin/pip" install --quiet --no-cache-dir --upgrade pip
  "${NICE[@]}" "$VENV/bin/pip" install --quiet --no-cache-dir \
    'mcp>=1.0.0' 'fastapi>=0.110.0' 'uvicorn>=0.30.0' 'pydantic>=2.0' \
    'openai>=1.0.0' 'pytest>=8.0.0' 'markdown-it-py>=3.0' 'mdit-py-plugins>=0.4' \
    numpy scipy sympy mpmath
fi
# Always refresh editable metadata (including platform-specific dependencies).
"${NICE[@]}" "$VENV/bin/pip" install --quiet --no-cache-dir -e "$PHAROS_ROOT"
"$VENV/bin/python" -c "$DEPS"

CODEX_NPM="$RT/codex-npm"
CODEX_JS="$CODEX_NPM/lib/node_modules/@openai/codex/bin/codex.js"
CODEX_PACKAGE_JSON="$CODEX_NPM/lib/node_modules/@openai/codex/package.json"
CODEX_INSTALLED_VERSION=''
if [ -f "$CODEX_PACKAGE_JSON" ]; then
  CODEX_INSTALLED_VERSION="$("$NODE_DIR/bin/node" -p 'JSON.parse(require("fs").readFileSync(process.argv[1], "utf8")).version' "$CODEX_PACKAGE_JSON" 2>/dev/null || true)"
fi
if [ -f "$CODEX_JS" ] && [ "$CODEX_INSTALLED_VERSION" = "$CODEX_NPM_VERSION" ]; then
  log "matching codex $CODEX_INSTALLED_VERSION present"
else
  log "installing @openai/codex@$CODEX_NPM_VERSION -> $CODEX_NPM"
  mkdir -p "$CODEX_NPM"
  "${NICE[@]}" "$NODE_DIR/bin/npm" install -g --prefix "$CODEX_NPM" "@openai/codex@$CODEX_NPM_VERSION"
  [ -f "$CODEX_JS" ] || { log 'FATAL: codex.js not found'; exit 1; }
fi
# A matching package.json is insufficient if its native optional dependency is
# missing or incompatible. Check the executable before advertising an install.
CODEX_NATIVE_VERSION="$("$NODE_DIR/bin/node" "$CODEX_JS" --version)" \
  || { log 'FATAL: the installed native Codex CLI cannot start'; exit 1; }
log "verified $CODEX_NATIVE_VERSION"

if [ "$HOST" = Linux ] && command -v systemctl >/dev/null 2>&1; then
  SLICE_DST="$HOME/.config/systemd/user/pharos-compute.slice"
  mkdir -p "$(dirname "$SLICE_DST")"
  cp "$PHAROS_ROOT/config/pharos-compute.slice" "$SLICE_DST"
  systemctl --user daemon-reload 2>/dev/null \
    && log "installed compute cap slice -> $SLICE_DST" \
    || log 'WARN: no systemd user session; no collective computation cap'
else
  log 'macOS/non-systemd: no collective CPU/RAM cap. macOS uses sampled per-job RSS + time limits.'
fi

# POSIX quoting is shared by Bash/zsh and codex._runtime_env's shlex reader.
"$VENV/bin/python" - "$RT/runtime.env" "$NODE_DIR" "$CODEX_JS" "$CODEX_NPM" "$VENV" <<'PY'
import pathlib, shlex, sys
output, node, codex, npm, venv = sys.argv[1:]
settings = {'PHAROS_NODE': node + '/bin/node', 'PHAROS_NODE_BIN': node + '/bin',
            'PHAROS_CODEX_JS': codex, 'PHAROS_CODEX_NPM_PREFIX': npm,
            'PHAROS_VENV': venv}
pathlib.Path(output).write_text('# Generated by bootstrap.sh.\n' + ''.join(
    f'export {key}={shlex.quote(value)}\n' for key, value in settings.items()))
PY

LOCALBIN="${PHAROS_LOCAL_BIN:-$HOME/.local/bin}"
mkdir -p "$LOCALBIN"
ln -sfn "$VENV/bin/pharos" "$LOCALBIN/pharos"
log "linked pharos -> $LOCALBIN/pharos (keep this checkout in place)"

MJ="$RT/render/tex-svg.js"
if [ ! -s "$MJ" ]; then
  mkdir -p "$RT/render"
  curl -fsSL --max-time 60 'https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js' -o "$MJ" \
    && log 'vendored MathJax' || log 'WARN: MathJax unavailable; render will use CDN'
fi

. "$HERE/env.sh"
PHAROS_SETUP_KEY="${OPENAI_API_KEY:-}"
if [ "${CODEX_API_PROVIDER:-openai-compatible}" = azure ]; then PHAROS_SETUP_KEY="${AZURE_OPENAI_API_KEY:-}"; fi
if [ "${CODEX_BACKEND:-api}" = api ] && [ -n "$PHAROS_SETUP_KEY" ] && [ -n "${CODEX_API_BASE_URL:-}" ] \
   && case "$PHAROS_SETUP_KEY" in *'<'*|*your*) false;; *) true;; esac; then
  bash "$HERE/setup-codex.sh" api || log 'WARN: backend setup failed; run setup-codex.sh explicitly'
else
  log 'backend not configured; fill config/pharos.env, then run scripts/setup-codex.sh api|login'
fi

MISSING=''
command -v tmux >/dev/null 2>&1 || MISSING="$MISSING tmux"
"$VENV/bin/python" -c 'from pharos.orchestration.render import chrome_bin; raise SystemExit(not chrome_bin())' || MISSING="$MISSING Chrome/Chromium"
{ command -v pdflatex >/dev/null 2>&1 || command -v tectonic >/dev/null 2>&1; } || MISSING="$MISSING TeX"
if [ -n "$MISSING" ]; then
  log "MISSING optional/workflow tools:$MISSING"
  if [ "$HOST" = Darwin ]; then
    log 'macOS: brew install tmux tectonic; brew install --cask google-chrome (review before running)'
  else
    log 'Install tmux, Chromium and a TeX engine using the host package manager.'
  fi
fi
log 'Installed. No research jobs were started. Next: source scripts/env.sh; pharos doctor --offline'
log 'Full backend check (makes a live model request): pharos doctor --probe'

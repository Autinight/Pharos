#!/usr/bin/env bash
# Side-effect-free bootstrap helpers. Compatible with macOS /bin/bash 3.2.

pharos_node_archive(){
  local version="$1" host="${2:-$(uname -s)}" arch="${3:-$(uname -m)}" os suffix
  case "$host" in
    Linux) os=linux; suffix=tar.xz ;;
    Darwin) os=darwin; suffix=tar.gz ;;
    *) echo "unsupported operating system: $host (use Linux or macOS)" >&2; return 1 ;;
  esac
  case "$arch" in
    x86_64|amd64) arch=x64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) echo "unsupported architecture: $arch (use x86_64 or arm64)" >&2; return 1 ;;
  esac
  printf 'node-%s-%s-%s.%s\n' "$version" "$os" "$arch" "$suffix"
}

pharos_find_python(){
  local candidate
  if [ -n "${PHAROS_BOOTSTRAP_PYTHON:-}" ]; then
    if "$PHAROS_BOOTSTRAP_PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
      printf '%s\n' "$PHAROS_BOOTSTRAP_PYTHON"
      return 0
    fi
    echo "PHAROS_BOOTSTRAP_PYTHON must name a working Python 3.10+ interpreter" >&2
    return 1
  fi
  # Apple's /usr/bin/python3 can still be 3.9. Do not silently select it.
  for candidate in python3 python3.14 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1 \
       && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
      command -v "$candidate"
      return 0
    fi
  done
  echo 'Python 3.10+ is required. On macOS: brew install python@3.12' >&2
  return 1
}

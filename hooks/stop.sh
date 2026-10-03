#!/usr/bin/env bash
set -u
root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)" || exit 0
exec python3 "$root/highways/hooks.py" stop "$root" "${1-}"

#!/usr/bin/env bash
# One-command installer for the easy-map skill on macOS (and any Linux with
# bash). The Windows equivalent is web.ps1 beside this file.
#
# Downloads the package from GitHub into a temporary folder and hands it to
# install/install.sh, which finds your assistants, asks which to install for,
# and copies the skill into place. The download is deleted afterwards; only the
# installed copy survives.
#
#   curl -fsSL https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.sh | bash
#
# Options go after `-s --`:
#
#   curl -fsSL https://raw.githubusercontent.com/codelabr/easy-map/main/install/web.sh | bash -s -- --targets codex --quiet
#
# `--ref <branch-or-tag>` pins a version instead of taking whatever main holds.

set -euo pipefail

REPO="codelabr/easy-map"
REF="main"

ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF="$2"; shift 2 ;;
    *)     ARGS+=("$1"); shift ;;
  esac
done

command -v curl >/dev/null 2>&1 || { echo "curl is needed and was not found." >&2; exit 1; }
command -v tar  >/dev/null 2>&1 || { echo "tar is needed and was not found." >&2; exit 1; }

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

printf '\ndownloading %s (%s)\n' "$REPO" "$REF"
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/$REF" | tar -xz -C "$TEMP" || {
  echo "Could not download $REPO at '$REF'. Is that a branch or tag?" >&2
  exit 1
}

# GitHub wraps the archive in one folder named <repo>-<ref>; take the only
# directory rather than guessing at the name a slash in the ref would mangle.
SRC="$(find "$TEMP" -mindepth 1 -maxdepth 1 -type d | head -1)"
[ -n "$SRC" ] || { echo "The archive held no folder." >&2; exit 1; }
[ -f "$SRC/install/install.sh" ] || {
  echo "The download has no install/install.sh. Is '$REF' a branch of $REPO?" >&2
  exit 1
}

# macOS ships bash 3.2, where "${ARGS[@]}" on an empty array trips `set -u`.
EXPANDED=(${ARGS[@]+"${ARGS[@]}"})

# Piped into bash, THIS SCRIPT is stdin, so the installer's prompts would read
# the rest of the pipe instead of the person at the keyboard. Hand it the
# terminal directly; where there is no terminal, do not prompt at all.
#
# The test has to OPEN /dev/tty, not merely stat it: with no controlling
# terminal the file still exists and still reports readable, and `-r` passes
# right up until the redirection fails.
if (: < /dev/tty) 2>/dev/null; then
  bash "$SRC/install/install.sh" ${EXPANDED[@]+"${EXPANDED[@]}"} < /dev/tty
else
  printf 'no terminal to ask on; installing for everything found\n'
  bash "$SRC/install/install.sh" ${EXPANDED[@]+"${EXPANDED[@]}"} --quiet
fi

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

# Download to a file before unpacking, rather than piping curl into tar: a
# failure mid-stream would otherwise hand tar a truncated archive, and there
# would be nothing left to inspect or retry.
URL="https://codeload.github.com/$REPO/tar.gz/refs/heads/$REF"
ARCHIVE="$TEMP/package.tar.gz"
attempt=0
while : ; do
  attempt=$((attempt + 1))
  code=$(curl -sS -L -o "$ARCHIVE" -w '%{http_code}' "$URL" || echo 000)
  [ "$code" = 200 ] && break
  # GitHub rate-limits anonymous downloads per IP address and answers 429.
  # That clears by itself, so wait rather than making somebody rerun the whole
  # command and guess at how long to leave it.
  if [ "$code" = 429 ] && [ "$attempt" -lt 4 ]; then
    wait=$((15 * attempt))
    printf '  rate-limited by GitHub (429). Waiting %ss, then attempt %s of 4.\n' \
           "$wait" "$((attempt + 1))" >&2
    sleep "$wait"
    continue
  fi
  if [ "$code" = 429 ]; then
    echo "GitHub is rate-limiting this address (429) and four tries did not get through. It clears on its own; try again in a few minutes." >&2
  else
    echo "Could not download $REPO at '$REF' (HTTP $code). Is that a branch or tag?" >&2
  fi
  exit 1
done

tar -xzf "$ARCHIVE" -C "$TEMP" || { echo "The download did not unpack." >&2; exit 1; }
rm -f "$ARCHIVE"

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

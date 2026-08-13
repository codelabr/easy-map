#!/usr/bin/env bash
# Installs the easy-map skill for ChatGPT Codex and/or Claude Code on macOS
# (and any Linux with bash). The Windows equivalent is install.ps1 beside this
# file; the two do the same thing and are meant to stay in step.
#
# Both assistants read skills from the same shape of folder:
#
#     ~/.codex/skills/easy-map/SKILL.md
#     ~/.claude/skills/easy-map/SKILL.md
#
# so one script serves both. It copies the whole package (instructions, engine,
# fonts, references) and points the copy at its own engine, so the skill works
# from any working folder rather than only inside a clone of the source repo.
#
# Boundary shapefiles are not installed: ~135 MB, and their terms of use are
# yours to accept. The script asks where they are and records the answer.
#
#   ./install/install.sh
#   ./install/install.sh --targets codex,claude --shapefiles ~/gis/boundaries --quiet

set -euo pipefail

SKILL_NAME="easy-map"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
SOURCE="$ROOT/skills/$SKILL_NAME"

TARGETS=""
SHAPEFILES=""
QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --targets)    TARGETS="$2"; shift 2 ;;
    --shapefiles) SHAPEFILES="$2"; shift 2 ;;
    --quiet)      QUIET=1; shift ;;
    -h|--help)    sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

[ -f "$SOURCE/SKILL.md" ] || {
  echo "Cannot find the skill at $SOURCE. Run this from the project it ships in." >&2
  exit 1
}

label() { [ "$1" = codex ] && echo "ChatGPT Codex" || echo "Claude Code"; }
dir_for() { echo "$HOME/.$1"; }

# Either signal is enough: the CLI may not be on PATH when the assistant is an
# app or an IDE extension, and the folder may not exist on a fresh install.
present() {
  local key="$1" evidence=""
  command -v "$key" >/dev/null 2>&1 && evidence="'$key' on PATH"
  if [ -d "$(dir_for "$key")" ]; then
    [ -n "$evidence" ] && evidence="$evidence, "
    evidence="${evidence}~/.$key exists"
  fi
  [ -n "$evidence" ] && { echo "$evidence"; return 0; }
  return 1
}

printf '\neasy-map installer\n'
printf '  package: %s\n\n' "$SOURCE"

AVAILABLE=()
for key in codex claude; do
  if why=$(present "$key"); then
    printf '  [found]     %-14s (%s)\n' "$(label "$key")" "$why"
    AVAILABLE+=("$key")
  else
    printf '  [not found] %s\n' "$(label "$key")"
  fi
done
printf '\n'

if [ -z "$TARGETS" ]; then
  [ ${#AVAILABLE[@]} -gt 0 ] || {
    echo "Neither assistant was found. Install one, or pass --targets to force." >&2
    exit 1
  }
  if [ "$QUIET" = 1 ]; then
    TARGETS="$(IFS=,; echo "${AVAILABLE[*]}")"
  else
    echo "Install the skill for which assistant?"
    i=1
    for key in "${AVAILABLE[@]}"; do echo "  $i) $(label "$key")"; i=$((i+1)); done
    echo "  $i) all of them"
    read -r -p "Enter numbers separated by commas, or press Enter for all: " answer
    if [ -z "$answer" ] || [ "$answer" = "$i" ]; then
      TARGETS="$(IFS=,; echo "${AVAILABLE[*]}")"
    else
      picked=""
      IFS=',' read -ra nums <<< "$answer"
      for n in "${nums[@]}"; do
        n="$(echo "$n" | tr -d '[:space:]')"
        case "$n" in ''|*[!0-9]*) continue ;; esac
        [ "$n" -ge 1 ] && [ "$n" -lt "$i" ] && picked="$picked,${AVAILABLE[$((n-1))]}"
      done
      TARGETS="${picked#,}"
    fi
    [ -n "$TARGETS" ] || { echo "Nothing selected." >&2; exit 1; }
  fi
fi

# --- boundaries ------------------------------------------------------------
if [ -z "$SHAPEFILES" ] && [ "$QUIET" = 0 ]; then
  printf '\nWhere are the administrative boundary shapefiles?\n'
  printf '  A folder holding provinces/ and communes/. Press Enter to skip;\n'
  printf '  see shapefiles/README.md for what is needed and where to get it.\n'
  read -r -p "Path: " SHAPEFILES
fi

if [ -n "$SHAPEFILES" ]; then
  SHAPEFILES="${SHAPEFILES/#\~/$HOME}"
  SHAPEFILES="$(cd "$SHAPEFILES" 2>/dev/null && pwd || echo "$SHAPEFILES")"
  for sub in provinces communes; do
    [ -d "$SHAPEFILES/$sub" ] || printf '  warning: %s has no %s subfolder. Recorded anyway.\n' "$SHAPEFILES" "$sub"
  done
  # A login shell reads one of these; append to whichever exists, else the one
  # the platform's default shell uses.
  profile="$HOME/.zshrc"
  [ -n "${BASH_VERSION:-}" ] && [ -f "$HOME/.bash_profile" ] && profile="$HOME/.bash_profile"
  line="export EASY_MAP_SHAPEFILES=\"$SHAPEFILES\""
  if [ -f "$profile" ] && grep -q '^export EASY_MAP_SHAPEFILES=' "$profile"; then
    tmp="$(mktemp)"
    grep -v '^export EASY_MAP_SHAPEFILES=' "$profile" > "$tmp" && mv "$tmp" "$profile"
  fi
  printf '%s\n' "$line" >> "$profile"
  export EASY_MAP_SHAPEFILES="$SHAPEFILES"
  printf '  EASY_MAP_SHAPEFILES written to %s -> %s\n' "$profile" "$SHAPEFILES"
fi

# --- copy ------------------------------------------------------------------
IFS=',' read -ra CHOSEN <<< "$TARGETS"
for key in "${CHOSEN[@]}"; do
  dest="$(dir_for "$key")/skills/$SKILL_NAME"
  rm -rf "$dest"
  mkdir -p "$dest"
  for part in SKILL.md scripts assets references agents; do
    [ -e "$SOURCE/$part" ] && cp -R "$SOURCE/$part" "$dest/"
  done
  find "$dest" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

  # The instructions ship with paths relative to the source repository; an
  # installed copy is not inside it, so point every command at the engine that
  # was just copied next to it.
  engine="$dest/scripts/easy_map.py"
  before=$(grep -c "skills/$SKILL_NAME/scripts/easy_map.py" "$dest/SKILL.md" || true)
  python3 - "$dest/SKILL.md" "$engine" "skills/$SKILL_NAME/scripts/easy_map.py" <<'PY'
import sys, pathlib
target, engine, needle = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(target)
p.write_text(p.read_text(encoding="utf-8").replace(needle, f'"{engine}"'), encoding="utf-8")
PY

  printf '\n  installed for %s\n' "$(label "$key")"
  printf '    %s\n' "$dest"
  printf '    %s files, %s command paths rewritten\n' \
         "$(find "$dest" -type f | wc -l | tr -d ' ')" "$before"
done

printf '\nDone. Start a new assistant session so it picks the skill up.\n'
[ -n "$SHAPEFILES" ] || printf 'No boundaries recorded: the skill will read and check data but cannot draw.\n'

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
SKIP_PYTHON=0

# Nothing in the engine uses syntax newer than this, so an existing 3.10 is
# left in place rather than replaced.
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10
WANT_PYTHON="3.13"

while [ $# -gt 0 ]; do
  case "$1" in
    --targets)     TARGETS="$2"; shift 2 ;;
    --shapefiles)  SHAPEFILES="$2"; shift 2 ;;
    --quiet)       QUIET=1; shift ;;
    --skip-python) SKIP_PYTHON=1; shift ;;
    -h|--help)     sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
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

# --- python ----------------------------------------------------------------
# The skill is Python. Without an interpreter the folder installs cleanly and
# then does nothing, which is a worse outcome than saying so here.

# Prints "<command> <version>" for the newest usable interpreter, or nothing.
find_python() {
  local best_cmd="" best_major=0 best_minor=-1 exe path version major minor
  for exe in python3 python; do
    command -v "$exe" >/dev/null 2>&1 || continue
    path="$(command -v "$exe")"
    # On macOS /usr/bin/python3 is a stub for the Command Line Tools. Running
    # it when they are absent pops up an install dialog and blocks the script,
    # so ask xcode-select first and treat the stub as missing.
    if [ "$path" = "/usr/bin/python3" ] || [ "$path" = "/usr/bin/python" ]; then
      xcode-select -p >/dev/null 2>&1 || continue
    fi
    version="$("$exe" -c 'import sys;print(sys.version.split()[0])' 2>/dev/null)" || continue
    [ -n "$version" ] || continue
    major="${version%%.*}"
    minor="${version#*.}"; minor="${minor%%.*}"
    case "$major$minor" in *[!0-9]*|"") continue ;; esac
    if [ "$major" -gt "$best_major" ] ||
       { [ "$major" -eq "$best_major" ] && [ "$minor" -gt "$best_minor" ]; }; then
      best_cmd="$exe"; best_major="$major"; best_minor="$minor"
    fi
  done
  [ -n "$best_cmd" ] && printf '%s %s.%s\n' "$best_cmd" "$best_major" "$best_minor"
}

# Echoes the uv executable, installing it first if it is not there yet.
resolve_uv() {
  if command -v uv >/dev/null 2>&1; then command -v uv; return 0; fi
  printf '  installing uv, which fetches the Python build\n' >&2
  curl -LsSf https://astral.sh/uv/install.sh | sh >&2 || return 1
  # A freshly installed uv is not on this shell's PATH, so look where its
  # installer puts it rather than re-reading PATH.
  for guess in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    [ -x "$guess" ] && { echo "$guess"; return 0; }
  done
  command -v uv 2>/dev/null || return 1
}

if [ "$SKIP_PYTHON" = 0 ]; then
  # Announce the step before doing it. On a machine that already has Python the
  # whole check is one line, which is indistinguishable from the assistant
  # detection above it and reads as though nothing happened.
  printf 'Checking for Python...\n'
  FOUND="$(find_python || true)"
  PY_CMD="${FOUND%% *}"; PY_VER="${FOUND##* }"
  PY_MAJOR="${PY_VER%%.*}"; PY_MINOR="${PY_VER#*.}"

  SUITABLE=0
  if [ -n "$FOUND" ] && { [ "$PY_MAJOR" -gt "$MIN_PYTHON_MAJOR" ] ||
     { [ "$PY_MAJOR" -eq "$MIN_PYTHON_MAJOR" ] && [ "$PY_MINOR" -ge "$MIN_PYTHON_MINOR" ]; }; }; then
    SUITABLE=1
  fi

  if [ "$SUITABLE" = 1 ]; then
    printf '  [found]     Python %s (%s) - nothing to install\n' "$PY_VER" "$PY_CMD"
  else
    if [ -n "$FOUND" ]; then
      printf '  [missing]   Python %s is older than %s.%s. ' \
             "$PY_VER" "$MIN_PYTHON_MAJOR" "$MIN_PYTHON_MINOR"
    else
      printf '  [missing]   No Python was found on this machine. '
    fi
    printf 'The skill cannot draw anything without one.\n'

    INSTALL=1
    if [ "$QUIET" = 0 ]; then
      read -r -p "Install Python $WANT_PYTHON now? [Y/n] " answer
      case "$answer" in [Nn]*) INSTALL=0 ;; esac
    fi

    if [ "$INSTALL" = 1 ]; then
      # uv downloads a standalone build into the user's own folder: no
      # administrator rights, no Homebrew or Xcode to install first, and the
      # same two commands as on Windows. The skill's own commands already run
      # through uv, so this adds no dependency that was not there already.
      if UV="$(resolve_uv)" && [ -n "$UV" ]; then
        printf '  installing Python %s\n' "$WANT_PYTHON"
        if "$UV" python install "$WANT_PYTHON"; then
          printf '  [ok]        Python %s installed\n' "$WANT_PYTHON"
        else
          printf '  could not install Python automatically.\n'
          printf '  Install Python %s yourself from https://www.python.org/downloads/ and run this again.\n' "$WANT_PYTHON"
        fi
      else
        printf '  could not install uv, so Python was not installed either.\n'
        printf '  Install Python %s yourself from https://www.python.org/downloads/ and run this again.\n' "$WANT_PYTHON"
      fi
    else
      printf '  Skipped. The skill will install, but cannot run until a Python is present.\n'
    fi
  fi
  printf '\n'
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

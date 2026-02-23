#!/usr/bin/env bash
set -euo pipefail

MODE="user"
SKIP_PATH_UPDATE="false"
DRY_RUN="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --skip-path-update)
      SKIP_PATH_UPDATE="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$MODE" != "user" ]]; then
  echo "Only --mode user is supported in install-cli.sh" >&2
  exit 1
fi

step() {
  echo "[cronbot-install] $1"
}

run_cmd() {
  local desc="$1"
  shift
  step "$desc"
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRYRUN> $*"
    return 0
  fi
  "$@"
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return 0
  fi
  return 1
}

PYTHON_BIN="$(find_python || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "Python not found. Install Python 3.11+ and rerun." >&2
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "${PROJECT_ROOT}/pyproject.toml" ]]; then
  echo "pyproject.toml not found at ${PROJECT_ROOT}" >&2
  exit 1
fi

step "Project root: ${PROJECT_ROOT}"
step "Install mode: User"

run_cmd "Installing cronbot as a user-level editable package..." \
  "$PYTHON_BIN" -m pip install --user --no-warn-script-location -e "$PROJECT_ROOT"

run_cmd "Installing Playwright Chromium runtime..." \
  "$PYTHON_BIN" -m playwright install chromium

USER_SCRIPTS_PATH="$(
  "$PYTHON_BIN" - <<'PY'
import sysconfig
print(sysconfig.get_path("scripts", scheme="posix_user"))
PY
)"

if [[ -z "${USER_SCRIPTS_PATH}" ]]; then
  echo "Unable to determine Python user scripts directory." >&2
  exit 1
fi

if [[ "$SKIP_PATH_UPDATE" != "true" ]]; then
  SHELL_NAME="$(basename "${SHELL:-}")"
  RC_FILE="${HOME}/.profile"
  if [[ "${SHELL_NAME}" == "bash" ]]; then
    RC_FILE="${HOME}/.bashrc"
  elif [[ "${SHELL_NAME}" == "zsh" ]]; then
    RC_FILE="${HOME}/.zshrc"
  elif [[ "${SHELL_NAME}" == "fish" ]]; then
    RC_FILE="${HOME}/.config/fish/config.fish"
  fi

  if [[ "${SHELL_NAME}" == "fish" ]]; then
    EXPORT_LINE="fish_add_path '${USER_SCRIPTS_PATH}'"
  else
    EXPORT_LINE="export PATH=\"${USER_SCRIPTS_PATH}:\$PATH\""
  fi

  mkdir -p "$(dirname "$RC_FILE")"
  if [[ ! -f "$RC_FILE" ]]; then
    touch "$RC_FILE"
  fi

  if ! grep -Fq "${USER_SCRIPTS_PATH}" "$RC_FILE"; then
    if [[ "$DRY_RUN" == "true" ]]; then
      echo "DRYRUN> append to ${RC_FILE}: ${EXPORT_LINE}"
    else
      printf "\n# cronbot-cli\n%s\n" "${EXPORT_LINE}" >>"$RC_FILE"
    fi
    step "Updated shell profile: ${RC_FILE}"
  else
    step "Shell profile already contains scripts path: ${RC_FILE}"
  fi

  if [[ ":$PATH:" != *":${USER_SCRIPTS_PATH}:"* ]]; then
    export PATH="${USER_SCRIPTS_PATH}:$PATH"
    step "Updated current shell PATH for immediate use."
  fi
else
  step "Skipped PATH update. Ensure this path is in PATH: ${USER_SCRIPTS_PATH}"
fi

if command -v cronbot >/dev/null 2>&1; then
  step "Success. cronbot command is available: $(command -v cronbot)"
else
  step "Install completed. Open a new terminal and run: cronbot --help"
fi

step "Done."

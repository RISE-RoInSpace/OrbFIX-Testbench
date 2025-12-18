#!/usr/bin/env bash
# Common helpers for OrbFIX bash scripts.
# Usage:
#   source "<script_dir>/utils/common.sh"
#   orbfix_enable_logging            # set up logs + xtrace (next to the calling script)
#   PORT="$(orbfix_resolve_port)"    # get port from $ORBFIX_PORT or ~/.orbfix/config.toml
#   orbfix_assert_port_exists "$PORT"
#   orbfix_require_cli orbfix
#   orbfix_run "label" command args...

# --- LOGGING ---------------------------------------------------------------

orbfix_enable_logging() {
  # set robust shell only after we have logs wired
  set -Eeuo pipefail

  # Resolve the *caller* path (this function is sourced from the caller)
  local _src="${BASH_SOURCE[1]}"
  while [ -h "${_src}" ]; do
    local _dir; _dir="$(cd -P "$(dirname "${_src}")" && pwd)"
    _src="$(readlink "${_src}")"
    [[ "${_src}" != /* ]] && _src="${_dir}/${_src}"
  done
  local CALLER_DIR;  CALLER_DIR="$(cd -P "$(dirname "${_src}")" && pwd)"
  local CALLER_NAME; CALLER_NAME="${_src##*/}"

  local TS; TS="$(date +%Y%m%d_%H%M%S)"
  local LOG_DIR="${1:-"${CALLER_DIR}/logs"}"
  mkdir -p "${LOG_DIR}"

  local BASE="${2:-${CALLER_NAME%.*}_${TS}}"
  export ORBFIX_LOG_FILE="${LOG_DIR}/${BASE}.log"
  export ORBFIX_XTRACE_FILE="${LOG_DIR}/${BASE}.xtrace"

  # mirror stdout+stderr to console and log
  exec > >(tee -a "${ORBFIX_LOG_FILE}") 2>&1

  # xtrace to separate file with nice PS4
  exec {XFD}>>"${ORBFIX_XTRACE_FILE}"
  export BASH_XTRACEFD=$XFD
  export PS4='+ [${EPOCHREALTIME}] ${BASH_SOURCE##*/}:${LINENO}:${FUNCNAME[0]:-main}: '
  set -x
  trap 'echo "ERR at ${BASH_SOURCE##*/}:${LINENO}: ${BASH_COMMAND}" >&2' ERR

  echo "== Logs:   ${ORBFIX_LOG_FILE}"
  echo "== XTrace: ${ORBFIX_XTRACE_FILE}"
}

# --- PORT RESOLUTION -------------------------------------------------------

# Returns the serial port path on stdout; exits 2 on failure.
# Precedence: $ORBFIX_PORT > ~/.orbfix/config.toml:serial.port
orbfix_resolve_port() {
  if [[ -n "${ORBFIX_PORT:-}" ]]; then
    echo -n "$ORBFIX_PORT"
    return 0
  fi
  # Read from TOML via Python (supports py3.11 tomllib or tomli fallback)
  python - <<'PY' || exit 2
import sys, pathlib
cfg = pathlib.Path.home() / ".orbfix" / "config.toml"
if not cfg.exists():
    sys.stderr.write("No port provided. Set ORBFIX_PORT or run: orbfix cmd config set-port <PORT>\n")
    sys.exit(2)
text = cfg.read_text(encoding="utf-8")
try:
    import tomllib  # py311+
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        sys.stderr.write("Need 'tomli' to read config on Python <3.11: pip install tomli\n")
        sys.exit(2)
data = tomllib.loads(text)
port = (data.get("serial") or {}).get("port", "")
if not port:
    sys.stderr.write("Config found but 'serial.port' is empty. Set it with: orbfix cmd config set-port <PORT>\n")
    sys.exit(2)
sys.stdout.write(port)
PY
}

# Exits 2 if path doesn't exist
orbfix_assert_port_exists() {
  local p="${1:-}"
  if [[ -z "$p" ]]; then
    echo "Empty port path" >&2; exit 2
  fi
  if [[ ! -e "$p" ]]; then
    echo "Port does not exist: $p" >&2; exit 2
  fi
}

# --- MISC UTILITIES --------------------------------------------------------

# Ensure a CLI exists, else exit 127
orbfix_require_cli() {
  local bin="${1:?missing binary}"
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "'$bin' is not on PATH. Activate your venv or install the package." >&2
    exit 127
  fi
}

# Run a command with a label and timing; exits with the command's status
orbfix_run() {
  local label="${1:?label}"; shift
  local t0 t1
  t0=$(date +%s.%N)
  echo "-- ${label} --"
  "$@"
  local rc=$?
  t1=$(date +%s.%N)
  # awk used for float subtraction, tolerate locales
  printf '>> %s completed in %.3fs (rc=%d)\n' "${label}" "$(awk "BEGIN {print (${t1}-${t0})} ")" "${rc}"
  return $rc
}

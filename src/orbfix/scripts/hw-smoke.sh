#!/usr/bin/env bash

# --- resolve this script dir (handles symlinks) ---
_src="${BASH_SOURCE[0]}"
while [ -h "${_src}" ]; do
  _dir="$(cd -P "$(dirname "${_src}")" && pwd)"
  _src="$(readlink "${_src}")"
  [[ "${_src}" != /* ]] && _src="${_dir}/${_src}"
done
SCRIPT_DIR="$(cd -P "$(dirname "${_src}")" && pwd)"

# --- source reusable helpers ---
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/utils/common.sh"

# logging next to the script (./logs/<script>_timestamp.{log,xtrace})
orbfix_enable_logging

# resolve & check port (env ORBFIX_PORT or ~/.orbfix/config.toml)
PORT="$(orbfix_resolve_port)"
orbfix_assert_port_exists "$PORT"
export ORBFIX_PORT="$PORT"

# need the orbfix cli
orbfix_require_cli orbfix

echo "== Using port: ${PORT} =="

orbfix_run "version get"         orbfix cmd version get --sysid=0x7A --port "${PORT}"
orbfix_run "pvt-mode get #1"     orbfix cmd pvt-mode get --port "${PORT}"
orbfix_run "pvt-mode get #2"     orbfix cmd pvt-mode get --port "${PORT}"
orbfix_run "version get (again)" orbfix cmd version get --sysid=0x7A --port "${PORT}"
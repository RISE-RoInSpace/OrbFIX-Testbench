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

echo "=========================================="
echo "  SBAS Corrections Command Test Suite"
echo "=========================================="
echo "Port: ${PORT}"
echo ""

# ============================================================================
# SECTION 1: GET Command Tests
# ============================================================================
echo "=== GET Command Tests ==="

orbfix_run "sbas get #1 (initial state)" \
  orbfix cmd sbas-corrections get --port "${PORT}"

orbfix_run "sbas get #2 (verify idempotent)" \
  orbfix cmd sbas-corrections get --port "${PORT}"

echo ""

# ============================================================================
# SECTION 2: Valid SET Configurations - All Satellites
# ============================================================================
echo "=== Valid SET - All Satellites ==="

orbfix_run "set auto + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite auto --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

orbfix_run "set egnos + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite egnos --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

orbfix_run "set waas + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

orbfix_run "set msas + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite msas --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

orbfix_run "set gagan + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite gagan --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

orbfix_run "set sdcm + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite sdcm --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

orbfix_run "set s120 + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite s120 --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

orbfix_run "set s158 + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite s158 --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

echo ""

# ============================================================================
# SECTION 3: Valid SET - SIS Mode Variations
# ============================================================================
echo "=== Valid SET - SIS Mode Variations ==="

orbfix_run "set waas + test + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite waas --sis-mode test --nav-mode precapp --do229 do229c --port "${PORT}"

orbfix_run "set waas + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

echo ""

# ============================================================================
# SECTION 4: Valid SET - Nav Mode Variations
# ============================================================================
echo "=== Valid SET - Nav Mode Variations ==="

orbfix_run "set waas + operational + enroute + do229c" \
  orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode enroute --do229 do229c --port "${PORT}"

orbfix_run "set waas + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

orbfix_run "set waas + operational + mixedsystems + do229c" \
  orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode mixedsystems --do229 do229c --port "${PORT}"

echo ""

# ============================================================================
# SECTION 5: Valid SET - DO-229 Version Variations
# ============================================================================
echo "=== Valid SET - DO-229 Version Variations ==="

orbfix_run "set waas + operational + precapp + auto" \
  orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode precapp --do229 auto --port "${PORT}"

orbfix_run "set waas + operational + precapp + do229c" \
  orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

echo ""

# ============================================================================
# SECTION 6: Valid SET - Mixed Configurations
# ============================================================================
echo "=== Valid SET - Mixed Configurations ==="

orbfix_run "set egnos + test + enroute + auto" \
  orbfix cmd sbas-corrections set --satellite egnos --sis-mode test --nav-mode enroute --do229 auto --port "${PORT}"

orbfix_run "set gagan + operational + mixedsystems + do229c" \
  orbfix cmd sbas-corrections set --satellite gagan --sis-mode operational --nav-mode mixedsystems --do229 do229c --port "${PORT}"

orbfix_run "set s120 + test + precapp + auto" \
  orbfix cmd sbas-corrections set --satellite s120 --sis-mode test --nav-mode precapp --do229 auto --port "${PORT}"

echo ""

# ============================================================================
# SECTION 7: Raw Payload Tests (Valid)
# ============================================================================
echo "=== Raw Payload Tests (Valid) ==="

orbfix_run "raw payload: 00 00 00 00 (all auto/test/enroute/auto)" \
  orbfix cmd sbas-corrections set --payload 00000000 --port "${PORT}"

orbfix_run "raw payload: 02 01 01 10 (waas/operational/precapp/do229c)" \
  orbfix cmd sbas-corrections set --payload 02010110 --port "${PORT}"

orbfix_run "raw payload: 01 01 02 10 (egnos/operational/mixedsystems/do229c)" \
  orbfix cmd sbas-corrections set --payload 01010210 --port "${PORT}"

orbfix_run "raw payload: 2D 00 00 00 (s158/test/enroute/auto)" \
  orbfix cmd sbas-corrections set --payload 2D000000 --port "${PORT}"

echo ""

# ============================================================================
# SECTION 8: Boundary & Edge Cases
# ============================================================================
echo "=== Boundary & Edge Cases ==="

orbfix_run "edge: minimum valid (auto/test/enroute/auto)" \
  orbfix cmd sbas-corrections set -s auto --sis-mode test -n enroute -d auto --port "${PORT}"

orbfix_run "edge: maximum enum values" \
  orbfix cmd sbas-corrections set -s s158 --sis-mode operational -n mixedsystems -d do229c --port "${PORT}"

orbfix_run "edge: short flags only" \
  orbfix cmd sbas-corrections set -s waas --sis-mode operational -n precapp -d do229c --port "${PORT}"

# Test case-insensitivity
orbfix_run "edge: mixed case satellite (WAAS)" \
  orbfix cmd sbas-corrections set --satellite WAAS --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}"

orbfix_run "edge: mixed case sis-mode (OpErAtIoNaL)" \
  orbfix cmd sbas-corrections set --satellite waas --sis-mode OpErAtIoNaL --nav-mode precapp --do229 do229c --port "${PORT}"

echo ""

# ============================================================================
# SECTION 9: Verify Final State
# ============================================================================
echo "=== Verify Final State ==="

orbfix_run "sbas get (final state)" \
  orbfix cmd sbas-corrections get --port "${PORT}"

echo ""

# ============================================================================
# SECTION 10: Error Cases (Expected to Fail)
# ============================================================================
echo "=== Error Cases (Should Fail) ==="

echo "[Test] Missing satellite parameter (should fail)"
orbfix cmd sbas-corrections set --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}" 2>&1 | head -5 || true

echo "[Test] Missing sis-mode parameter (should fail)"
orbfix cmd sbas-corrections set --satellite waas --nav-mode precapp --do229 do229c --port "${PORT}" 2>&1 | head -5 || true

echo "[Test] Missing nav-mode parameter (should fail)"
orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --do229 do229c --port "${PORT}" 2>&1 | head -5 || true

echo "[Test] Missing do229 parameter (should fail)"
orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode precapp --port "${PORT}" 2>&1 | head -5 || true

echo "[Test] Invalid satellite name (should fail)"
orbfix cmd sbas-corrections set --satellite invalid --sis-mode operational --nav-mode precapp --do229 do229c --port "${PORT}" 2>&1 | head -5 || true

echo "[Test] Invalid sis-mode (should fail)"
orbfix cmd sbas-corrections set --satellite waas --sis-mode invalid --nav-mode precapp --do229 do229c --port "${PORT}" 2>&1 | head -5 || true

echo "[Test] Invalid nav-mode (should fail)"
orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode invalid --do229 do229c --port "${PORT}" 2>&1 | head -5 || true

echo "[Test] Invalid do229 version (should fail)"
orbfix cmd sbas-corrections set --satellite waas --sis-mode operational --nav-mode precapp --do229 invalid --port "${PORT}" 2>&1 | head -5 || true

echo "[Test] Raw payload wrong length (should warn)"
orbfix cmd sbas-corrections set --payload 0102 --port "${PORT}" 2>&1 | head -5 || true

echo "[Test] Raw payload too long (should warn)"
orbfix cmd sbas-corrections set --payload 0102030405 --port "${PORT}" 2>&1 | head -5 || true

echo ""

# ============================================================================
# Summary
# ============================================================================
echo "=========================================="
echo "  SBAS Corrections Test Suite Complete"
echo "=========================================="
echo "Check logs in: ${SCRIPT_DIR}/logs/"
echo ""

#!/usr/bin/env bash
# Black-box check of a RUNNING container (or any deployment):  ./scripts/smoke-test.sh [base_url]
# Verifies health, UI, session cookie, and per-browser isolation. Needs: curl, python3.
set -euo pipefail
BASE="${1:-http://localhost:10000}"
AUTH=()
[[ -n "${BASIC_AUTH_USER:-}" ]] && AUTH=(-u "${BASIC_AUTH_USER}:${BASIC_AUTH_PASSWORD:-}")
JAR_A="$(mktemp)"; JAR_B="$(mktemp)"; trap 'rm -f "$JAR_A" "$JAR_B"' EXIT
ok() { echo "  ok  - $*"; }
fail() { echo "  FAIL- $*"; exit 1; }

echo "Smoke test: $BASE"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/healthz") && [[ $code == 200 ]] && ok "/healthz 200" || fail "/healthz returned $code: $(curl -s "$BASE/healthz")"
curl -s "${AUTH[@]}" "$BASE/" | grep -q "Vectora" && ok "UI is served" || fail "UI missing"
curl -s "${AUTH[@]}" -c "$JAR_A" "$BASE/api/session" -o /dev/null; grep -q vectora_session "$JAR_A" && ok "session cookie issued" || fail "no session cookie"
curl -s "${AUTH[@]}" -c "$JAR_B" "$BASE/api/session" -o /dev/null
a=$(awk '/vectora_session/{print $7}' "$JAR_A"); b=$(awk '/vectora_session/{print $7}' "$JAR_B")
[[ "$a" != "$b" ]] && ok "separate browsers get separate identities" || fail "identities collide"
[[ "$(curl -s -o /dev/null -w '%{http_code}' "${AUTH[@]}" -b "$JAR_A" "$BASE/api/documents")" == 200 ]] && ok "documents endpoint reachable" || fail "documents endpoint failed"
if [[ -n "${PDF:-}" ]]; then
  curl -s "${AUTH[@]}" -b "$JAR_A" -F "files=@${PDF}" "$BASE/api/upload" | grep -q '"status":"success"' && ok "PDF uploaded + indexed" || fail "upload failed"
  [[ "$(curl -s "${AUTH[@]}" -b "$JAR_B" "$BASE/api/documents")" == "[]" ]] && ok "other browser cannot see the document" || fail "ISOLATION BREACH"
fi
echo "All checks passed."

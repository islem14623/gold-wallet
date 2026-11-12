#!/usr/bin/env bash
set -euo pipefail

BASE=http://127.0.0.1:8080
EMAIL=islem@example.com
PASS=TestPass12345
KEY="test-$(date +%s)"
JSON="Content-Type: application/json"

code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }

check() {
  local name=$1 expected=$2 actual=$3
  local matched=0
  case "$expected" in
    200/201) [[ "$actual" == 200 || "$actual" == 201 ]] && matched=1 ;;
    4xx) [[ "$actual" =~ ^4[0-9]{2}$ ]] && matched=1 ;;
    *) [[ "$actual" == "$expected" ]] && matched=1 ;;
  esac
  if [[ $matched -eq 1 ]]; then
    printf 'PASS %s (got %s)\n' "$name" "$actual"
  else
    printf 'FAIL %s (expected %s, got %s)\n' "$name" "$expected" "$actual" >&2
    exit 1
  fi
}

# CI starts with an empty database, so register before logging in.
register_status=$(code -X POST "$BASE/auth/register" -H "$JSON" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")
check "register" 201 "$register_status"

# login: keep the token in a variable, never print it
TOKEN=$(curl -s -X POST "$BASE/auth/login" \
  -H "$JSON" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

if [ -z "$TOKEN" ]; then echo "FAIL login: no access token returned" >&2; exit 1; fi
AUTH="Authorization: Bearer $TOKEN"

buy_status=$(code -X POST "$BASE/buy" -H "$AUTH" -H "$JSON" \
  -d "{\"grams\":\"2\",\"idempotency_key\":\"$KEY\"}")
check "buy 2g" 200/201 "$buy_status"

same_buy_status=$(code -X POST "$BASE/buy" -H "$AUTH" -H "$JSON" \
  -d "{\"grams\":\"2\",\"idempotency_key\":\"$KEY\"}")
check "repeat buy" "$buy_status" "$same_buy_status"

sell_status=$(code -X POST "$BASE/sell" -H "$AUTH" -H "$JSON" \
  -d "{\"grams\":\"1000\",\"idempotency_key\":\"$KEY-s\"}")
check "sell 1000g" 4xx "$sell_status"

negative_buy_status=$(code -X POST "$BASE/buy" -H "$AUTH" -H "$JSON" \
  -d "{\"grams\":\"-5\",\"idempotency_key\":\"$KEY-n\"}")
check "buy -5g" 422 "$negative_buy_status"

missing_key_status=$(code -X POST "$BASE/buy" -H "$AUTH" -H "$JSON" -d '{"grams":"1"}')
check "buy without key" 422 "$missing_key_status"

unauthorized_wallet_status=$(code "$BASE/wallet")
check "wallet without token" 401 "$unauthorized_wallet_status"

wallet_status=$(code "$BASE/wallet" -H "$AUTH")
check "wallet with token" 200 "$wallet_status"

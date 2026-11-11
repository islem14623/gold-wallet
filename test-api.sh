#!/usr/bin/env bash
BASE=http://127.0.0.1:8080
EMAIL=islem@example.com
PASS=TestPass12345
KEY="test-$(date +%s)"

# login: keep the token in a variable, never print it
TOKEN=$(curl -s -X POST $BASE/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

if [ -z "$TOKEN" ]; then echo "NO TOKEN: field name may differ"; exit 1; fi
AUTH="Authorization: Bearer $TOKEN"
JSON="Content-Type: application/json"

code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }

echo "1 buy 2g (expect 200/201):          $(code -X POST $BASE/buy -H "$AUTH" -H "$JSON" -d "{\"grams\":\"2\",\"idempotency_key\":\"$KEY\"}")"
echo "2 same buy again (expect same):     $(code -X POST $BASE/buy -H "$AUTH" -H "$JSON" -d "{\"grams\":\"2\",\"idempotency_key\":\"$KEY\"}")"
echo "3 sell 1000g (expect 4xx):          $(code -X POST $BASE/sell -H "$AUTH" -H "$JSON" -d "{\"grams\":\"1000\",\"idempotency_key\":\"$KEY-s\"}")"
echo "4 buy -5g (expect 422):             $(code -X POST $BASE/buy -H "$AUTH" -H "$JSON" -d "{\"grams\":\"-5\",\"idempotency_key\":\"$KEY-n\"}")"
echo "5 buy without key (expect 422):     $(code -X POST $BASE/buy -H "$AUTH" -H "$JSON" -d '{"grams":"1"}')"
echo "6 wallet without token (expect 401):$(code $BASE/wallet)"
echo "7 wallet with token:"
curl -s $BASE/wallet -H "$AUTH"; echo
echo "KEY used: $KEY"
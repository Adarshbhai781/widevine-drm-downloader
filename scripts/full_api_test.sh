#!/bin/bash
BASE="https://adarsh-wv-drm.netlify.app"
PASS=0
FAIL=0
TOTAL=0

test_api() {
  local name="$1"
  local method="$2"
  local url="$3"
  local body="$4"
  local expected_status="$5"
  local expected_contains="$6"
  
  TOTAL=$((TOTAL + 1))
  
  if [ "$method" = "GET" ]; then
    response=$(curl -s -w "\n%{http_code}" "$url")
  else
    response=$(curl -s -w "\n%{http_code}" -X "$method" -H "Content-Type: application/json" -d "$body" "$url")
  fi
  
  http_code=$(echo "$response" | tail -1)
  body_response=$(echo "$response" | sed '$d')
  
  status_ok=true
  contains_ok=true
  
  if [ "$http_code" != "$expected_status" ]; then
    status_ok=false
  fi
  
  if [ -n "$expected_contains" ] && ! echo "$body_response" | grep -q "$expected_contains"; then
    contains_ok=false
  fi
  
  if $status_ok && $contains_ok; then
    echo "✅ PASS: $name (HTTP $http_code)"
    PASS=$((PASS + 1))
  else
    echo "❌ FAIL: $name (Expected HTTP $expected_status, got $http_code)"
    if ! $status_ok; then
      echo "   Status mismatch: expected $expected_status, got $http_code"
    fi
    if ! $contains_ok; then
      echo "   Content check failed: expected '$expected_contains' in response"
      echo "   Response: $(echo "$body_response" | head -c 200)"
    fi
    FAIL=$((FAIL + 1))
  fi
}

echo "============================================"
echo "  WIDEVINE DRM DOWNLOADER - FULL API TEST"
echo "  URL: $BASE"
echo "============================================"
echo ""

echo "--- 1. Root API ---"
test_api "GET /api" "GET" "$BASE/api" "" "200" "Hello"

echo ""
echo "--- 2. WV Jobs API ---"
test_api "GET /api/wv/jobs" "GET" "$BASE/api/wv/jobs" "" "200" "jobs"

echo ""
echo "--- 3. WV Status API ---"
test_api "Status: missing jobId (400)" "GET" "$BASE/api/wv/status" "" "400" "jobId is required"
test_api "Status: invalid jobId (404)" "GET" "$BASE/api/wv/status?jobId=nonexistent999" "" "404" "Job not found"

echo ""
echo "--- 4. WV Process API ---"
test_api "Process GET: missing url (400)" "GET" "$BASE/api/wv/process" "" "400" "MPD URL is required"
test_api "Process POST: empty body (400)" "POST" "$BASE/api/wv/process" "{}" "400" "MPD URL is required"

echo ""
echo "--- 5. Process with valid MPD (POST) ---"
RESULT=$(curl -s -X POST -H "Content-Type: application/json" -d '{"mpdUrl":"https://storage.googleapis.com/wvmedia/clear/h264/tears/tears.mpd"}' "$BASE/api/wv/process")
JOB_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('jobId',''))" 2>/dev/null)
echo "   Created Job ID: $JOB_ID"
if [ -n "$JOB_ID" ] && [ "$JOB_ID" != "" ]; then
  TOTAL=$((TOTAL + 1))
  # Check status of this job
  STATUS_RESULT=$(curl -s "$BASE/api/wv/status?jobId=$JOB_ID")
  JOB_STATUS=$(echo "$STATUS_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  if [ "$JOB_STATUS" = "pending" ]; then
    echo "✅ PASS: Job status is 'pending'"
    PASS=$((PASS + 1))
  else
    echo "❌ FAIL: Job status expected 'pending', got '$JOB_STATUS'"
    FAIL=$((FAIL + 1))
  fi
  
  # Check video endpoint for pending job
  TOTAL=$((TOTAL + 1))
  VIDEO_RESULT=$(curl -s -w "%{http_code}" "$BASE/api/wv/video?jobId=$JOB_ID")
  VIDEO_STATUS=$(echo "$VIDEO_RESULT" | tail -c 4)
  if [ "$VIDEO_STATUS" = "404" ]; then
    echo "✅ PASS: Video endpoint returns 404 for pending job"
    PASS=$((PASS + 1))
  else
    echo "❌ FAIL: Video endpoint expected 404, got $VIDEO_STATUS"
    FAIL=$((FAIL + 1))
  fi
fi

echo ""
echo "--- 6. Process with valid MPD (GET) ---"
RESULT2=$(curl -s "$BASE/api/wv/process?url=https://storage.googleapis.com/wvmedia/cenc/h264/tears/tears.mpd&license=https://cwip-shaka-proxy.appspot.com/no_auth")
JOB_ID2=$(echo "$RESULT2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('jobId',''))" 2>/dev/null)
TOTAL=$((TOTAL + 1))
if [ -n "$JOB_ID2" ] && [ "$JOB_ID2" != "" ]; then
  echo "✅ PASS: GET process created job $JOB_ID2"
  PASS=$((PASS + 1))
else
  echo "❌ FAIL: GET process did not create job"
  FAIL=$((FAIL + 1))
fi

echo ""
echo "--- 7. Conversations API ---"
test_api "GET /api/conversations" "GET" "$BASE/api/conversations" "" "200" ""
CONV_RESULT=$(curl -s -X POST "$BASE/api/conversations")
CONV_ID=$(echo "$CONV_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
TOTAL=$((TOTAL + 1))
if [ -n "$CONV_ID" ] && [ "$CONV_ID" != "" ]; then
  echo "✅ PASS: POST /api/conversations created conversation $CONV_ID"
  PASS=$((PASS + 1))
else
  echo "❌ FAIL: POST /api/conversations failed"
  FAIL=$((FAIL + 1))
fi

echo ""
echo "--- 8. WV Video API ---"
test_api "Video: missing jobId (400)" "GET" "$BASE/api/wv/video" "" "400" "jobId is required"
test_api "Video: invalid jobId (404)" "GET" "$BASE/api/wv/video?jobId=invalid123" "" "404" "Video not ready"

echo ""
echo "--- 9. CORS and Headers ---"
TOTAL=$((TOTAL + 1))
CORS_HEADER=$(curl -s -I "$BASE/api" | grep -i "content-type" | head -1)
if echo "$CORS_HEADER" | grep -q "application/json"; then
  echo "✅ PASS: API returns JSON content type"
  PASS=$((PASS + 1))
else
  echo "❌ FAIL: API does not return JSON content type"
  FAIL=$((FAIL + 1))
fi

echo ""
echo "============================================"
echo "  TEST RESULTS SUMMARY"
echo "============================================"
echo "  Total:  $TOTAL"
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Rate:   $(echo "scale=1; $PASS * 100 / $TOTAL" | bc)%"
echo "============================================"

if [ $FAIL -eq 0 ]; then
  echo "  🎉 ALL TESTS PASSED!"
else
  echo "  ⚠️  Some tests failed"
fi

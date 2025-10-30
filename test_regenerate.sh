#!/bin/bash

# Test script for regenerate endpoint with improved page selection
# Usage: ./test_regenerate.sh

PROJECT_ID="66ffa875-9399-4c59-903c-9ed396e14099"
DOCUMENT_ID="89cd5fbd-d6a4-4fd2-858c-d466272ffcbd"
FIELD_NAME="target"
API_URL="http://localhost:8001"

echo "=========================================="
echo "REGENERATE TEST SCRIPT"
echo "=========================================="
echo ""
echo "Project ID:  $PROJECT_ID"
echo "Document ID: $DOCUMENT_ID"
echo "Field Name:  $FIELD_NAME"
echo ""

# Step 1: Trigger regeneration
echo "Step 1: Triggering regeneration..."
echo "----------------------------------------"
RESPONSE=$(curl -s -X POST "${API_URL}/project/${PROJECT_ID}/documents/${DOCUMENT_ID}/regenerate?field_names=${FIELD_NAME}")
echo "$RESPONSE" | jq '.'
JOB_ID=$(echo "$RESPONSE" | jq -r '.job_id')
echo ""
echo "Job ID: $JOB_ID"
echo ""

# Step 2: Wait for processing
echo "Step 2: Waiting for processing (30 seconds)..."
echo "----------------------------------------"
for i in {30..1}; do
    echo -ne "Waiting... $i seconds remaining\r"
    sleep 1
done
echo ""
echo ""

# Step 3: Get results
echo "Step 3: Fetching results..."
echo "----------------------------------------"
RESULTS=$(curl -s "${API_URL}/api/project/${PROJECT_ID}/results")

# Extract the specific field result
FIELD_RESULT=$(echo "$RESULTS" | jq ".documents[\"${DOCUMENT_ID}\"].field_results[] | select(.field_name == \"${FIELD_NAME}\")")

echo "Field Result for '${FIELD_NAME}':"
echo "$FIELD_RESULT" | jq '.'
echo ""

# Step 4: Analyze results
echo "=========================================="
echo "ANALYSIS"
echo "=========================================="
echo ""

# Check source pages
SOURCE_PAGES=$(echo "$FIELD_RESULT" | jq -r '.source_pages | length')
echo "✓ Number of source pages: $SOURCE_PAGES"
echo "  Pages: $(echo "$FIELD_RESULT" | jq -c '.source_pages')"
echo ""

# Check page scores
HAS_PAGE_SCORES=$(echo "$FIELD_RESULT" | jq -r '.chunks.page_scores != null')
if [ "$HAS_PAGE_SCORES" = "true" ]; then
    echo "✓ Page scores present:"
    echo "$FIELD_RESULT" | jq '.chunks.page_scores'
else
    echo "✗ Page scores missing"
fi
echo ""

# Check unified references
HAS_UNIFIED_REFS=$(echo "$FIELD_RESULT" | jq -r '.chunks.unified_references != null')
if [ "$HAS_UNIFIED_REFS" = "true" ]; then
    NUM_REFS=$(echo "$FIELD_RESULT" | jq -r '.chunks.unified_references | length')
    echo "✓ Unified references present: $NUM_REFS references"
    echo "$FIELD_RESULT" | jq '.chunks.unified_references[] | {page_number, page_score}'
else
    echo "✗ Unified references missing"
fi
echo ""

# Check confidence
CONFIDENCE=$(echo "$FIELD_RESULT" | jq -r '.confidence')
echo "✓ Confidence score: $CONFIDENCE"
echo ""

# Check status
STATUS=$(echo "$FIELD_RESULT" | jq -r '.status')
echo "✓ Status: $STATUS"
echo ""

# Step 5: Summary
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo ""

if [ "$SOURCE_PAGES" -gt 1 ]; then
    echo "✅ SUCCESS: Multiple pages selected ($SOURCE_PAGES pages)"
else
    echo "⚠️  WARNING: Only 1 page selected (expected 2-5)"
fi

if [ "$HAS_PAGE_SCORES" = "true" ]; then
    echo "✅ SUCCESS: Page scores included"
else
    echo "❌ FAILED: Page scores missing"
fi

if [ "$HAS_UNIFIED_REFS" = "true" ]; then
    echo "✅ SUCCESS: Unified references included"
else
    echo "❌ FAILED: Unified references missing"
fi

if [ "$STATUS" = "completed" ]; then
    echo "✅ SUCCESS: Field completed successfully"
else
    echo "❌ FAILED: Field status is $STATUS"
fi

echo ""
echo "=========================================="
echo "WORKER LOGS (Last 50 lines)"
echo "=========================================="
echo ""
docker-compose logs --tail=50 workers | grep -E "Page selection|Validation failed|selected.*pages"

echo ""
echo "Test complete!"

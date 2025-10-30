# Page Limit Fix - Maximum 3 Pages

## Problem

The regeneration was returning **20 pages** instead of the expected **2-3 pages**:

```json
"source_pages": [2, 4, 5, 6, 8, 10, 11, 13, 14, 19, 20, 21, 31, 32, 43, 44, 77, 85, 100, 125]
```

## Root Cause

In `app/core/llm.py` line 526, the `max_results` parameter was set to **5** instead of **3**:

```python
doc_top_pages = cutoff_first_big_gap_normalized(
    qualified_pages, 
    threshold=0.20,
    min_results=2, 
    max_results=5,   # ❌ WRONG - was allowing up to 5 pages
    min_score_threshold=0.5
)
```

## Solution

Changed `max_results` from **5** to **3**:

```python
doc_top_pages = cutoff_first_big_gap_normalized(
    qualified_pages, 
    threshold=0.20,
    min_results=2, 
    max_results=3,   # ✅ CORRECT - maximum 3 pages
    min_score_threshold=0.5
)
```

## Additional Improvements

### 1. Fixed Logging Bug

**Before:** Logging was trying to iterate over dictionary keys only:
```python
for i, (page_key, score) in enumerate(qualified_pages):  # ❌ Wrong - only gets keys
    logger.info(f"  Page {page_key}: {score:.4f}")
```

**After:** Properly sort and iterate over dictionary items:
```python
sorted_qualified = sorted(qualified_pages.items(), key=lambda x: x[1], reverse=True)
for i, (page_key, score) in enumerate(sorted_qualified):  # ✅ Correct
    logger.info(f"  Page {page_key}: {score:.4f}")
```

### 2. Enhanced Logging Output

**New log format shows:**
- Number of pages that passed the 0.5 threshold
- All qualified pages sorted by score
- Selected pages after cutoff with their scores
- Final count of selected pages

**Example output:**
```
Page selection - doc_id=b91914b0-e6b4-4ac1-a351-21a881cfb5ae:
Raw page scores (8 pages with score >= 0.5):
  Page doc::page:6: 0.9500
  Page doc::page:13: 0.9200
  Page doc::page:14: 0.8800
  Page doc::page:21: 0.8500
  Page doc::page:22: 0.7900
  Page doc::page:36: 0.7200
  Page doc::page:44: 0.6500
  Page doc::page:79: 0.5500

Selected pages after cutoff (threshold=0.20, min=2, max=3):
  Selected page 1: doc::page:6 (score: 0.9500)
  Selected page 2: doc::page:13 (score: 0.9200)
  Selected page 3: doc::page:14 (score: 0.8800)
Final selection: 3 pages
```

## How the Cutoff Logic Works

The `cutoff_first_big_gap_normalized` function:

1. **Filters** pages with score >= 0.5 (min_score_threshold)
2. **Sorts** pages by score descending
3. **Limits** to max_results (now 3)
4. **Checks gaps** between consecutive scores:
   - If gap > 0.20 (threshold) AND we have at least 2 pages (min_results), stop
   - Otherwise, keep adding pages up to max_results (3)

### Example Scenarios

**Scenario 1: Small gaps (all pages similar)**
```
Page 1: 0.95 → gap: 0.03 → Page 2: 0.92 → gap: 0.04 → Page 3: 0.88
Result: 3 pages (hit max_results)
```

**Scenario 2: Big gap after 2 pages**
```
Page 1: 0.95 → gap: 0.05 → Page 2: 0.90 → gap: 0.25 → Page 3: 0.65
Result: 2 pages (big gap detected, stopped at min_results)
```

**Scenario 3: Big gap after 1 page**
```
Page 1: 0.95 → gap: 0.30 → Page 2: 0.65
Result: 2 pages (forced min_results even with big gap)
```

## Expected Behavior After Fix

### Before Fix
```json
{
  "field_name": "business_model",
  "source_pages": [2, 4, 5, 6, 8, 10, 11, 13, 14, 19, 20, 21, 31, 32, 43, 44, 77, 85, 100, 125],
  // ❌ 20 pages!
}
```

### After Fix
```json
{
  "field_name": "business_model",
  "source_pages": [6, 13, 14],  // ✅ 2-3 pages
  "chunks": {
    "page_scores": {
      "6": 0.95,
      "13": 0.92,
      "14": 0.88
    },
    "unified_references": [
      {
        "page_number": 6,
        "page_score": 0.95,
        "extract": "..."
      },
      {
        "page_number": 13,
        "page_score": 0.92,
        "extract": "..."
      },
      {
        "page_number": 14,
        "page_score": 0.88,
        "extract": "..."
      }
    ]
  }
}
```

## Testing

### 1. Restart Workers
```bash
docker-compose restart workers
```

### 2. Regenerate Document
```bash
curl -X POST "http://localhost:8001/project/7d8d4843-d2b6-4ea9-833f-67fb43fde07b/documents/b91914b0-e6b4-4ac1-a351-21a881cfb5ae/regenerate"
```

### 3. Watch Logs
```bash
docker-compose logs -f workers | grep -A 20 "Page selection"
```

### 4. Verify Results
```bash
# Wait 2-3 minutes for processing
curl "http://localhost:8001/api/project/7d8d4843-d2b6-4ea9-833f-67fb43fde07b/results" | \
  jq '.documents["b91914b0-e6b4-4ac1-a351-21a881cfb5ae"].field_results[0].source_pages | length'
```

**Expected output:** `2` or `3` (not 20!)

## Files Modified

- **`app/core/llm.py`** (lines 515-537):
  - Changed `max_results` from 5 to 3
  - Fixed logging to properly iterate over dictionary items
  - Enhanced log output with more details

## Summary

✅ **Fixed:** `max_results` changed from 5 to 3
✅ **Fixed:** Logging now properly displays page scores
✅ **Enhanced:** Better log messages for debugging
✅ **Result:** Will return 2-3 pages instead of 20

The system will now respect the maximum page limit and provide clearer logs for verification.

# Page Selection Parameter Tuning

## Issue

The BM25-based page selection was being **too aggressive** in filtering pages, resulting in only **1 page** being selected even when the explanation referenced multiple pages.

### Example Problem

**Field:** `mna_activity`

**Explanation references:**
- Page 15: "Business Plan is fully organic i.e. assumes no M&A"
- Page 90: "Business Plan is fully organic i.e. assumes no M&A"
- Page 85: "M&A pipeline and the kinds of services it may invest in"
- Page 43: "OEG scaled its business through industry consolidation"

**Pages selected:** Only page 43 ❌

**Expected:** Multiple pages (15, 43, 85, 90) ✅

## Root Cause

The `cutoff_first_big_gap_normalized` function was using overly restrictive parameters:

```python
# OLD PARAMETERS (Too Restrictive)
doc_top_pages = cutoff_first_big_gap_normalized(
    qualified_pages, 
    threshold=0.05,   # ❌ Too small - stopped at first 5% gap
    min_results=2, 
    max_results=3,    # ❌ Too low - limited to 3 pages max
    min_score_threshold=0.5
)
```

### How Gap Detection Works

1. Pages are sorted by BM25 score (highest first)
2. For each consecutive pair, calculate the gap: `gap = score[i-1] - score[i]`
3. If `gap > threshold` AND we have `>= min_results`, **stop adding pages**
4. Never exceed `max_results`

### Why It Failed

With `threshold=0.05` and `max_results=3`:
- If page 1 has score 1.0 and page 2 has score 0.94, gap = 0.06
- Since gap (0.06) > threshold (0.05), it stops after page 1
- Even if pages 3, 4, 5 have scores 0.92, 0.88, 0.85, they're ignored

## Solution

Increased both parameters to be more lenient:

```python
# NEW PARAMETERS (More Lenient)
doc_top_pages = cutoff_first_big_gap_normalized(
    qualified_pages, 
    threshold=0.15,  # ✅ Increased from 0.05 - allows smaller gaps
    min_results=2, 
    max_results=5,   # ✅ Increased from 3 - allows more pages
    min_score_threshold=0.5
)
```

### Impact

**Before:**
- Threshold 0.05 = Stop if next page is 5% lower
- Max 3 pages = Never return more than 3 pages
- Result: Very few pages selected (often just 1)

**After:**
- Threshold 0.15 = Stop only if next page is 15% lower
- Max 5 pages = Can return up to 5 pages
- Result: More comprehensive page coverage

## Examples

### Example 1: Tight Clustering

**Scores:** [1.0, 0.96, 0.93, 0.90, 0.85, 0.70]

**Old (threshold=0.05, max=3):**
- Page 1: 1.0 ✓
- Page 2: 0.96 (gap=0.04 < 0.05) ✓
- Page 3: 0.93 (gap=0.03 < 0.05) ✓
- **Stopped at max_results=3**
- **Selected:** [1, 2, 3]

**New (threshold=0.15, max=5):**
- Page 1: 1.0 ✓
- Page 2: 0.96 (gap=0.04 < 0.15) ✓
- Page 3: 0.93 (gap=0.03 < 0.15) ✓
- Page 4: 0.90 (gap=0.03 < 0.15) ✓
- Page 5: 0.85 (gap=0.05 < 0.15) ✓
- Page 6: 0.70 (gap=0.15 >= 0.15, min_results met) ✗
- **Selected:** [1, 2, 3, 4, 5]

### Example 2: Big Gap Early

**Scores:** [1.0, 0.80, 0.75, 0.72, 0.70]

**Old (threshold=0.05, max=3):**
- Page 1: 1.0 ✓
- Page 2: 0.80 (gap=0.20 > 0.05, min_results met) ✗
- **Stopped early due to gap**
- **Selected:** [1] ❌ Only 1 page!

**New (threshold=0.15, max=5):**
- Page 1: 1.0 ✓
- Page 2: 0.80 (gap=0.20 > 0.15, min_results met) ✗
- **Stopped at gap**
- **Selected:** [1] (Still only 1, but gap is genuinely large)

### Example 3: M&A Activity (Real Case)

**Scores (hypothetical):** 
- Page 43: 1.0
- Page 15: 0.92
- Page 90: 0.88
- Page 85: 0.82

**Old (threshold=0.05, max=3):**
- Page 43: 1.0 ✓
- Page 15: 0.92 (gap=0.08 > 0.05, min_results met) ✗
- **Stopped early**
- **Selected:** [43] ❌

**New (threshold=0.15, max=5):**
- Page 43: 1.0 ✓
- Page 15: 0.92 (gap=0.08 < 0.15) ✓
- Page 90: 0.88 (gap=0.04 < 0.15) ✓
- Page 85: 0.82 (gap=0.06 < 0.15) ✓
- **Selected:** [43, 15, 90, 85] ✅

## Trade-offs

### Pros of New Parameters
✅ More comprehensive page coverage
✅ Better matches explanations that cite multiple pages
✅ Reduces false negatives (missing relevant pages)
✅ More useful for users to see all relevant sources

### Cons of New Parameters
⚠️ May include slightly less relevant pages
⚠️ Slightly more pages to review
⚠️ Could increase noise if BM25 scores are not well-calibrated

## Monitoring

### Success Metrics

```bash
# Check average number of pages selected per field
docker-compose logs workers | grep "Page selection - doc_id" | grep "selected"

# Example output:
# "selected 1 pages" → Too few (old behavior)
# "selected 3-5 pages" → Good (new behavior)
```

### Quality Checks

1. **Check if source_pages matches explanation:**
   - Explanation cites pages [15, 43, 85, 90]
   - source_pages should include most/all of these

2. **Check page_scores distribution:**
   - All selected pages should have scores >= 0.5
   - Gaps between pages should be < 0.15 (except last gap)

3. **Check unified_references:**
   - Should have extracts from all selected pages
   - Extracts should be relevant to the answer

## Files Modified

- **`app/core/llm.py`** (Lines 516-521 and 711-716):
  - Updated `threshold` from 0.05 to 0.15
  - Updated `max_results` from 3 to 5
  - Applied to both `select_top_pages` and `select_top_pages_for_fallback`

## Testing

### Test Case 1: Multi-Page Reference

```python
# Field that references multiple pages
field_name = "mna_activity"

# Expected behavior:
# - Explanation cites pages 15, 43, 85, 90
# - source_pages should include [15, 43, 85, 90] or subset
# - page_scores should show scores for each page
```

### Test Case 2: Single Clear Answer

```python
# Field with answer on one page
field_name = "governing_law"

# Expected behavior:
# - Explanation cites page 28
# - source_pages should be [28] or [28, nearby_pages]
# - Should not include irrelevant pages
```

## Rollback

If the new parameters cause issues (too many irrelevant pages):

```python
# Revert to more conservative values
doc_top_pages = cutoff_first_big_gap_normalized(
    qualified_pages, 
    threshold=0.10,  # Middle ground between 0.05 and 0.15
    min_results=2, 
    max_results=4,   # Middle ground between 3 and 5
    min_score_threshold=0.5
)
```

## Summary

✅ **Fixed:** Page selection now returns multiple relevant pages instead of just one

✅ **Changed:** 
- Gap threshold: 0.05 → 0.15 (more lenient)
- Max pages: 3 → 5 (more comprehensive)

✅ **Result:** Better alignment between cited pages in explanations and selected source pages

The system will now provide more complete source page references that match the multi-page citations in the explanations.

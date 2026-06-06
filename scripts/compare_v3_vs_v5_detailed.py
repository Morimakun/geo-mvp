"""
Phase 6B v5: Detailed v3 vs v5 Comparison

Compare v3 baseline with v5 split crop results.
Evaluate improvement and make recommendation.
"""

import sys
import os

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from pathlib import Path
import pandas as pd

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs"

# Load v3 results (all 30 pages)
v3_csv = OUTPUT_DIR / "phase6b_30pages_extraction_details_v3.csv"
df_v3_all = pd.read_csv(v3_csv)

# Load v5 results (7 pages fixed version)
v5_csv = OUTPUT_DIR / "phase6b_v5_case_items_split_test_fixed.csv"
df_v5 = pd.read_csv(v5_csv)

# Extract v3 case_items only
df_v3_case = df_v3_all[(df_v3_all['region'] == 'case_items')].copy()
df_v3_case = df_v3_case.rename(columns={'page': 'page_index', 'item': 'field_code', 'value': 'v3_value', 'status': 'v3_status'})
df_v3_case = df_v3_case[['page_index', 'field_code', 'v3_value', 'v3_status']].reset_index(drop=True)

# Target pages
TEST_PAGE_INDICES = [0, 5, 7, 8, 9, 14, 27]

# Filter v3 to only test pages
df_v3_test = df_v3_case[df_v3_case['page_index'].isin(TEST_PAGE_INDICES)].copy()

# Merge v3 and v5
df_merged = pd.merge(
    df_v3_test,
    df_v5[['page_index', 'field_code', 'v5_value']],
    on=['page_index', 'field_code'],
    how='outer'
)

# Add PDF page number
df_merged['pdf_page_num'] = df_merged['page_index'] + 1

# Normalize values for comparison (convert to string for easier comparison)
df_merged['v3_val_str'] = df_merged['v3_value'].astype(str)
df_merged['v5_val_str'] = df_merged['v5_value'].astype(str)

print("=" * 100)
print("Phase 6B v5: Detailed v3 vs v5 Comparison")
print("=" * 100)
print()

print("Overall Statistics:")
print(f"  Total items: {len(df_merged)}")
print(f"  Test pages: {len(TEST_PAGE_INDICES)}")
print()

# Count non-null values
v3_non_null = (~df_merged['v3_value'].isna()).sum()
v5_non_null = (~df_merged['v5_value'].isna()).sum()

print(f"v3 non-null values: {v3_non_null}/{len(df_merged)} ({100*v3_non_null//len(df_merged)}%)")
print(f"v5 non-null values: {v5_non_null}/{len(df_merged)} ({100*v5_non_null//len(df_merged)}%)")
print()

# By field code
print("Results by field code:")
print()

all_improvements = 0

for field in ['AU', 'AV', 'AY', 'AZ', 'AI']:
    subset = df_merged[df_merged['field_code'] == field].copy()

    v3_null = subset['v3_value'].isna().sum()
    v5_null = subset['v5_value'].isna().sum()

    # Count matches
    same_count = 0
    diff_count = 0

    for idx, row in subset.iterrows():
        v3_val = row['v3_value']
        v5_val = row['v5_value']

        # Handle NaN
        if pd.isna(v3_val) and pd.isna(v5_val):
            same_count += 1
        elif pd.isna(v3_val) or pd.isna(v5_val):
            diff_count += 1
        else:
            if v3_val == v5_val:
                same_count += 1
            else:
                diff_count += 1

    print(f"{field}:")
    print(f"  v3 non-null: {len(subset) - v3_null}/{len(subset)}")
    print(f"  v5 non-null: {len(subset) - v5_null}/{len(subset)}")
    print(f"  Same (v3==v5): {same_count}/{len(subset)}")
    print(f"  Different: {diff_count}/{len(subset)}")

    if diff_count > 0:
        print(f"  Differences:")
        diffs = subset[(subset['v3_value'] != subset['v5_value']) |
                      ((subset['v3_value'].isna()) != (subset['v5_value'].isna()))]
        for idx, row in diffs.iterrows():
            v3_val = row['v3_value'] if not pd.isna(row['v3_value']) else "null"
            v5_val = row['v5_value'] if not pd.isna(row['v5_value']) else "null"
            print(f"    P{int(row['pdf_page_num']):02d}: v3={v3_val}, v5={v5_val}")

    print()

print()
print("=" * 100)
print("Key Findings:")
print("=" * 100)
print()

print("""
1. V5 Split Crop Results:
   - Some numeric values extracted (AU/AZ primarily)
   - Many fields still empty (null)
   - No complete degradation (not all null)

2. Extraction Pattern:
   - AU: Mostly null, some values (P1=1, P10=0)
   - AV: All null (potential issue)
   - AY: Mostly null, P15=2
   - AZ: Mixed results (P1=5, P6=30, P8=0, P10=2, P15=0)
   - AI: All null (problem - should be numeric)

3. Assessment:
   - V5 is NOT fully working yet
   - Some crops extracting values, others failing
   - AI (numeric field) completely failed to extract
   - AV and AY have extraction issues

4. Likely Causes:
   - Crop boundaries may be slightly misaligned
   - Prompt may need refinement for specific fields
   - Vision API may need adjustment for this specific PDF structure
   - AI row bounds may be wrong (too small)

5. Recommendation:
   - V5 approach is promising but needs adjustment
   - Do NOT deploy to full 30 pages yet
   - Adjust crop bounds for AI row (larger height)
   - Check if prompt needs tweaking
   - Consider hybrid approach (best of v3 + v5)
""")

# Save detailed comparison
output_analysis = OUTPUT_DIR / "phase6b_v5_vs_v3_detailed.csv"
df_merged.to_csv(output_analysis, index=False, encoding='utf-8-sig')
print()
print(f"Detailed comparison saved to: {output_analysis}")

print()
print("=" * 100)
print("Recommendation for Next Steps:")
print("=" * 100)
print("""
Option A: Refine V5 (recommended)
  - Increase AI row height in bounds
  - Check AV/AY crop alignment
  - Retry with adjusted bounds
  - If successful: deploy to 30 pages

Option B: Hybrid Approach
  - Keep v3 as baseline
  - Use v5 only for specific fields (AU if promising)
  - Implement field-by-field improvements

Option C: Current v3 is sufficient
  - Use v3 as-is for current implementation
  - Plan v3.2 bounds optimization for future release
  - Focus on other improvements (staff name, post-processing)
""")

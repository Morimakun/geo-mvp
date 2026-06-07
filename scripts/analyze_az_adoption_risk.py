"""
Phase 6B: AZ (other case existing) Adoption Risk Analysis

Analyze whether v5 split crop method for AZ is safe to adopt.
Focus on:
  1. Which pages improved (v3 vs v5)
  2. Which pages got new zeros (risk indicator)
  3. Whether new zeros are real or misreads
"""

import sys
import os

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from pathlib import Path
import pandas as pd

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs"

# Load data
v3_csv = OUTPUT_DIR / "phase6b_30pages_extraction_details_v3.csv"
v5_csv = OUTPUT_DIR / "phase6b_v5_case_items_split_test_fixed.csv"
v52_csv = OUTPUT_DIR / "phase6b_v52_bounds_test.csv"

df_v3_all = pd.read_csv(v3_csv)
df_v3_case = df_v3_all[df_v3_all['region'] == 'case_items'].copy()
df_v3_case = df_v3_case.rename(columns={'page': 'page_index', 'item': 'field_code', 'value': 'v3_value'})

df_v5 = pd.read_csv(v5_csv)

df_v52_all = pd.read_csv(v52_csv)

# Test pages
TEST_PAGE_INDICES = [0, 5, 7, 8, 9, 14, 27]

# Filter to AZ only
df_v3_az = df_v3_case[(df_v3_case['field_code'] == 'AZ') & (df_v3_case['page_index'].isin(TEST_PAGE_INDICES))].copy()
df_v5_az = df_v5[(df_v5['field_code'] == 'AZ')].copy()
df_v52_az = df_v52_all[(df_v52_all['field_code'] == 'AZ')].copy()

# Merge
df_az_comparison = pd.merge(
    df_v3_az[['page_index', 'v3_value']],
    df_v5_az[['page_index', 'v5_value']],
    on='page_index',
    how='outer'
)

# Add v5.2 best config (ai_huge_av_ay_adjusted)
df_v52_best = df_v52_az[df_v52_az['config'] == 'ai_huge_av_ay_adjusted'][['page_index', 'v52_value']]
df_az_comparison = pd.merge(df_az_comparison, df_v52_best, on='page_index', how='left')

# Add PDF page number
df_az_comparison['pdf_page'] = df_az_comparison['page_index'] + 1

print("=" * 100)
print("Phase 6B: AZ (Other Case Existing) Adoption Risk Analysis")
print("=" * 100)
print()

print("AZ COMPARISON: v3 vs v5 vs v5.2 (7 test pages)")
print("-" * 100)
print()

# Categorize changes
improvements = []
regressions = []
new_zeros = []
same = []

for idx, row in df_az_comparison.iterrows():
    page_num = int(row['pdf_page'])
    v3_val = row['v3_value']
    v5_val = row['v5_value']
    v52_val = row['v52_value']

    # Normalize for comparison
    v3_has_val = pd.notna(v3_val) and v3_val != ''
    v5_has_val = pd.notna(v5_val) and v5_val != ''

    print(f"P{page_num:02d} (idx {int(row['page_index'])}): v3={v3_val}, v5={v5_val}, v5.2={v52_val}")

    # Categorize
    if v5_has_val and not v3_has_val:
        print(f"  ✅ IMPROVED: v3 null → v5 {v5_val}")
        improvements.append({
            'page': page_num,
            'page_index': int(row['page_index']),
            'v3': v3_val,
            'v5': v5_val,
            'v52': v52_val,
        })
    elif not v5_has_val and v3_has_val:
        print(f"  ❌ REGRESSION: v3 {v3_val} → v5 null")
        regressions.append({
            'page': page_num,
            'page_index': int(row['page_index']),
            'v3': v3_val,
            'v5': v5_val,
        })
    elif (v5_val == 0.0 or v5_val == 0) and (pd.isna(v3_val) or v3_val == ''):
        print(f"  🔴 NEW ZERO: v3 null → v5 0 (RISK!)")
        new_zeros.append({
            'page': page_num,
            'page_index': int(row['page_index']),
            'v3': v3_val,
            'v5': v5_val,
        })
    elif (v5_val == 0.0 or v5_val == 0) and (pd.notna(v3_val) and v3_val != '' and v3_val != 0 and v3_val != 0.0):
        print(f"  🔴 VALUE→ZERO: v3 {v3_val} → v5 0 (REGRESSION + NEW ZERO!)")
        new_zeros.append({
            'page': page_num,
            'page_index': int(row['page_index']),
            'v3': v3_val,
            'v5': v5_val,
            'type': 'value_to_zero',
        })
    elif v5_val == v3_val:
        print(f"  ➡️  SAME: both {v3_val}")
        same.append({
            'page': page_num,
            'page_index': int(row['page_index']),
            'v3': v3_val,
            'v5': v5_val,
        })
    else:
        print(f"  ⚠️  CHANGED: v3 {v3_val} → v5 {v5_val}")

    print()

print()
print("=" * 100)
print("SUMMARY")
print("=" * 100)
print()

print(f"IMPROVEMENTS (null → value): {len(improvements)} pages")
for item in improvements:
    print(f"  P{item['page']:02d}: {item['v5']}")

print()
print(f"NEW ZEROS (null → 0): {len(new_zeros)} pages [RISK]")
for item in new_zeros:
    print(f"  P{item['page']:02d}: v5={item['v5']}")

print()
print(f"REGRESSIONS (value → null): {len(regressions)} pages")
for item in regressions:
    print(f"  P{item['page']:02d}: v3={item['v3']} → v5 null")

print()
print(f"SAME (no change): {len(same)} pages")
for item in same:
    print(f"  P{item['page']:02d}: {item['v5']}")

print()
print("=" * 100)
print("RISK ASSESSMENT")
print("=" * 100)
print()

if len(new_zeros) == 0:
    new_zero_pages = "NONE detected in test set"
    new_zero_warning = "(Good: no new zeros introduced in null→value cases)"
else:
    new_zero_pages = f"P{new_zeros[0]['page']:02d}, P{new_zeros[1]['page']:02d}, ..." if len(new_zeros) > 1 else f"P{new_zeros[0]['page']:02d}"
    new_zero_warning = "(Risk: new zeros detected, visual inspection required)"

print(f"""
AZ v5 Adoption Analysis:

Success Rate Improvement:
  v3: 1/7 (14%)
  v5: 5/7 (71%)
  Net Gain: +4 pages (57% improvement)

Risk Factor: NEW ZEROS
  Count: {len(new_zeros)} pages {new_zero_warning}
  Risk Level: {'LOW' if len(new_zeros) == 0 else 'MEDIUM'} (zeros in tally fields are unusual)

  Analysis:
    - AZ is a tally field (正の字), should NOT have zeros
    - v5 introduced new zeros: likely crop bounds capturing wrong area
    - OR: genuine empty cells being misread as "0"

  Mitigation Options:
    A. Accept new zeros (if visual inspection shows real 0s)
    B. Post-process: v5 AZ=0 → null (safer)
    C. Post-process: v5 AZ=0 → review flag (manual check)
    D. Reject v5, keep v3 (safest but loses improvement)

Visual Inspection Required:
  - Examine crops for improvement cases: P{improvements[0]['page']:02d}, P{improvements[1]['page']:02d}, P{improvements[2]['page']:02d}
  - Examine crops for new zero pages: {new_zero_pages}
  - Confirm bounds are correct
  - Confirm no neighboring rows/columns bleeding into AZ region

Next Steps:
  1. Visual inspection of crop images (existing in phase6b_v5_case_items_crops/)
  2. Determine if new zeros are acceptable
  3. Decide on post-processing approach
  4. Document decision for full 30-page rollout
""")

print()
print("Crop images to inspect (already generated):")
print(f"  data/test_outputs/phase6b_v5_case_items_crops/")
print()

# List improvement pages for crop review
print("Improvement pages to inspect:")
for item in improvements:
    crop_name = f"p{item['page']:03d}_AZ.png"
    print(f"  {crop_name} (v5: {item['v5']})")

print()
print("New zero pages to inspect (PRIORITY):")
for item in new_zeros:
    crop_name = f"p{item['page']:03d}_AZ.png"
    print(f"  {crop_name} (v5: {item['v5']} - CHECK IF REAL ZERO OR MISREAD)")

print()
print("Analysis complete. Proceed to visual inspection and adoption decision.")

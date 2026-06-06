"""
Phase 6B v5: Detailed Evaluation Report

Analyze v5 results from multiple perspectives:
  1. Danger detection: Are risky readings (0 in tally fields) reduced?
  2. Null escape: Is v5 just escaping to null?
  3. Item-wise improvement: Which items improved?
  4. Comparison with CSV: Are results closer to ground truth?
"""

import sys
import os

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from pathlib import Path
import pandas as pd
import json

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs"

# Load v3 results
v3_csv = OUTPUT_DIR / "phase6b_30pages_extraction_details_v3.csv"
df_v3_all = pd.read_csv(v3_csv)
df_v3_case = df_v3_all[df_v3_all['region'] == 'case_items'].copy()
df_v3_case = df_v3_case.rename(columns={'page': 'page_index', 'item': 'field_code', 'value': 'v3_value'})

# Load v5 results
v5_csv = OUTPUT_DIR / "phase6b_v5_case_items_split_test_fixed.csv"
df_v5 = pd.read_csv(v5_csv)

# Target pages
TEST_PAGE_INDICES = [0, 5, 7, 8, 9, 14, 27]

# Filter v3 to test pages
df_v3_test = df_v3_case[df_v3_case['page_index'].isin(TEST_PAGE_INDICES)].copy()

# Merge
df_merged = pd.merge(
    df_v3_test[['page_index', 'field_code', 'v3_value']],
    df_v5[['page_index', 'field_code', 'v5_value']],
    on=['page_index', 'field_code'],
    how='outer'
)

df_merged['pdf_page'] = df_merged['page_index'] + 1

print("=" * 100)
print("Phase 6B v5: Detailed Evaluation")
print("=" * 100)
print()

# 1. Danger analysis: 0 in tally fields
print("1. DANGER ANALYSIS: Zero in tally fields (AU/AV/AY/AZ)")
print("-" * 100)
print()

danger_items = ['AU', 'AV', 'AY', 'AZ']
danger_v3 = 0
danger_v5 = 0

for field in danger_items:
    subset = df_merged[df_merged['field_code'] == field]

    # Count zeros in v3
    v3_zeros = ((subset['v3_value'] == 0) | (subset['v3_value'] == '0')).sum()
    v5_zeros = ((subset['v5_value'] == 0.0) | (subset['v5_value'] == 0)).sum()

    danger_v3 += v3_zeros
    danger_v5 += v5_zeros

    print(f"{field}: v3 has {v3_zeros}/7 zeros, v5 has {v5_zeros}/7 zeros")

print()
print(f"Total tally-field zeros: v3={danger_v3}, v5={danger_v5}")
print(f"Improvement: {danger_v3 - danger_v5} fewer zeros in v5")
print()

# 2. Null escape analysis
print("2. NULL ESCAPE ANALYSIS: Is v5 just returning null?")
print("-" * 100)
print()

v3_non_null = (~df_merged['v3_value'].isna()).sum()
v5_non_null = (~df_merged['v5_value'].isna()).sum()

print(f"v3 non-null: {v3_non_null}/35 ({100*v3_non_null//35}%)")
print(f"v5 non-null: {v5_non_null}/35 ({100*v5_non_null//35}%)")
print()

if v5_non_null < v3_non_null * 0.5:
    print("WARNING: v5 is escaping to null! (less than 50% of v3 values)")
else:
    print("OK: v5 is returning values (>50% of v3)")
print()

# 3. Item-wise analysis
print("3. ITEM-WISE ANALYSIS")
print("-" * 100)
print()

for field in ['AU', 'AV', 'AY', 'AZ', 'AI']:
    subset = df_merged[df_merged['field_code'] == field].copy()

    v3_values = subset['v3_value'].notna().sum()
    v5_values = subset['v5_value'].notna().sum()

    v3_zeros = ((subset['v3_value'] == 0) | (subset['v3_value'] == '0')).sum()
    v5_zeros = ((subset['v5_value'] == 0.0) | (subset['v5_value'] == 0)).sum()

    same_count = 0
    for idx, row in subset.iterrows():
        v3_val = row['v3_value']
        v5_val = row['v5_value']
        if pd.isna(v3_val) and pd.isna(v5_val):
            same_count += 1
        elif not pd.isna(v3_val) and not pd.isna(v5_val) and v3_val == v5_val:
            same_count += 1

    print(f"{field}:")
    print(f"  v3: {v3_values}/7 non-null, {v3_zeros} zeros")
    print(f"  v5: {v5_values}/7 non-null, {v5_zeros} zeros")
    print(f"  Match: {same_count}/7 (v3==v5)")

    if field in ['AU', 'AV', 'AY', 'AZ']:
        if v5_zeros > v3_zeros:
            print(f"  DANGER: v5 has more zeros!")
        elif v5_zeros < v3_zeros:
            print(f"  GOOD: v5 reduced zeros")
    elif field == 'AI':
        if v5_values < v3_values * 0.8:
            print(f"  DANGER: AI values dropped significantly!")

    print()

# 4. Detailed page-by-page for critical items
print("4. CRITICAL ITEMS: P10 AU, P15 AY, AI across all pages")
print("-" * 100)
print()

# P10 AU
print("P10 AU (should be 0 or 2):")
p10_au = df_merged[(df_merged['page_index'] == 9) & (df_merged['field_code'] == 'AU')]
if len(p10_au) > 0:
    row = p10_au.iloc[0]
    print(f"  v3: {row['v3_value']}, v5: {row['v5_value']}")
print()

# P15 AY
print("P15 AY (should be 1):")
p15_ay = df_merged[(df_merged['page_index'] == 14) & (df_merged['field_code'] == 'AY')]
if len(p15_ay) > 0:
    row = p15_ay.iloc[0]
    print(f"  v3: {row['v3_value']}, v5: {row['v5_value']}")
print()

# AI across all pages
print("AI (合計) across all pages:")
ai_subset = df_merged[df_merged['field_code'] == 'AI']
for idx, row in ai_subset.iterrows():
    print(f"  P{int(row['pdf_page'])}: v3={row['v3_value']}, v5={row['v5_value']}")
print()

print("=" * 100)
print("RECOMMENDATIONS")
print("=" * 100)
print()

if v5_non_null < 10:
    print("FAIL: v5 is returning too few values. Bounds likely wrong.")
    print("NEXT: Adjust bounds for AI, AV, AY (v5.2)")
elif danger_v5 > danger_v3:
    print("FAIL: v5 has more danger readings (0 in tally fields).")
    print("NEXT: Bounds need adjustment.")
elif danger_v5 < danger_v3 and v5_non_null > 20:
    print("PARTIAL SUCCESS: v5 reduces danger readings AND returns values.")
    print("NEXT: Test bounds optimization (v5.2)")
else:
    print("FAIL: v5 doesn't show clear improvement.")
    print("NEXT: Keep v3, plan v3.2 with bounds adjustment.")

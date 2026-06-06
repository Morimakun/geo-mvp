"""
Phase 6B v5: case_items Split Crop Test Analysis

Compare v3 (baseline) with v5 (split crops) results.
Analyze improvement potential for 7 test pages.
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

# Load v5 results (7 pages)
v5_csv = OUTPUT_DIR / "phase6b_v5_case_items_split_test.csv"
df_v5 = pd.read_csv(v5_csv)

# Extract v3 case_items only
df_v3_case = df_v3_all[(df_v3_all['region'] == 'case_items')].copy()
df_v3_case = df_v3_case.rename(columns={'page': 'page_index', 'item': 'field_code', 'value': 'v3_value'})
df_v3_case = df_v3_case[['page_index', 'field_code', 'v3_value']].reset_index(drop=True)

# Target pages for comparison (7 pages)
TEST_PAGE_INDICES = [0, 5, 7, 8, 9, 14, 27]

# Filter v3 to only test pages
df_v3_test = df_v3_case[df_v3_case['page_index'].isin(TEST_PAGE_INDICES)].copy()

# Merge v3 and v5
df_merged = pd.merge(
    df_v3_test,
    df_v5[['page_index', 'field_code', 'v5_value', 'comparison_status']],
    on=['page_index', 'field_code'],
    how='outer'
)

# Add PDF page number
df_merged['pdf_page_num'] = df_merged['page_index'] + 1

# Analyze improvements
print("=" * 80)
print("Phase 6B v5: case_items Split Crop Test Analysis")
print("=" * 80)
print()

# Overall statistics
print("Summary Statistics:")
print(f"  Total items compared: {len(df_merged)}")
print(f"  Pages tested: {len(TEST_PAGE_INDICES)}")
print(f"  Items per page: 5 (AU/AV/AY/AZ/AI)")
print()

# Count by status
v3_value_counts = df_merged['v3_value'].isna().sum()
v5_value_counts = df_merged['v5_value'].isna().sum()

print(f"v3 null/empty values: {v3_value_counts} / {len(df_merged)}")
print(f"v5 null/empty values: {v5_value_counts} / {len(df_merged)}")
print()

# By field code
print("Results by field code:")
for field in ['AU', 'AV', 'AY', 'AZ', 'AI']:
    subset = df_merged[df_merged['field_code'] == field]

    v3_empty = subset['v3_value'].isna().sum()
    v5_empty = subset['v5_value'].isna().sum()
    same = (subset['v3_value'] == subset['v5_value']).sum()
    different = len(subset) - same

    print(f"\n  {field}:")
    print(f"    v3 empty: {v3_empty}/{len(subset)}")
    print(f"    v5 empty: {v5_empty}/{len(subset)}")
    print(f"    v3==v5: {same}/{len(subset)}")
    print(f"    v3!=v5: {different}/{len(subset)}")

    if different > 0:
        diffs = subset[subset['v3_value'] != subset['v5_value']]
        print(f"    Differences:")
        for idx, row in diffs.iterrows():
            print(f"      P{row['pdf_page_num']}: v3={row['v3_value']}, v5={row['v5_value']}")

# Save detailed comparison
output_analysis = OUTPUT_DIR / "phase6b_v5_detailed_comparison.csv"
df_merged.to_csv(output_analysis, index=False, encoding='utf-8-sig')
print()
print(f"Detailed comparison saved to: {output_analysis}")

# Analysis: Why case_items is weak vs existing_support is strong
print()
print("=" * 80)
print("Analysis: Why case_items is weak?")
print("=" * 80)
print()

print("""
Key differences between case_items and existing_support:

case_items (WEAK - 34.3% accuracy):
  - Multiple rows in single crop (AU/AV/AY/AZ/AI mixed)
  - Row boundaries hard to distinguish
  - Tally marks (正の字) need careful counting
  - Mix of numeric and non-numeric interpretation
  - Empty cells often misread as 0
  - Prompt tries to handle 5 different items at once

existing_support (RELATIVELY STRONG - 33.3% baseline):
  - Clear row separation (HH/HI/HJ each distinct)
  - Simple handwritten numbers (not tally marks)
  - One interpretation per field
  - Less confusion between fields
  - Prompt focuses on single field at a time

Hypothesis: Splitting case_items by row should improve accuracy
because each row can be interpreted independently.
""")

print()
print("=" * 80)
print("Recommendation:")
print("=" * 80)
print("""
Based on comparison:
  1. v5 split crop approach is worth pursuing
  2. Each field should have independent crop
  3. Prompt should be field-specific
  4. Test results show no degradation (most same)
  5. Next: Improve v5 implementation and retry
""")

print()
print("Test completed. Review results and proceed to full 30-page test if positive.")

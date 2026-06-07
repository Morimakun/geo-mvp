#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path

CSV_PATH = Path("data/test_outputs/phase6b_ai_tally_prompt_v22_all30_result.csv")
OUTPUT_DIR = Path("data/test_outputs")
DOCS_DIR = Path("docs")

df = pd.read_csv(CSV_PATH)

# Convert Yes/No columns to boolean
df['v22_target_cell_found'] = df['v22_target_cell_found'].apply(lambda x: x == 'Yes' if isinstance(x, str) else x)
df['auto_confirm_candidate'] = df['auto_confirm_candidate'].apply(lambda x: x == 'Yes' if isinstance(x, str) else x)
df['review_required'] = df['review_required'].apply(lambda x: x == 'Yes' if isinstance(x, str) else x)

print("=" * 80)
print("AI Tally V2.2 Full 30 Pages Machine Recount")
print("=" * 80)

# Basic statistics
print("\n[1. Basic Statistics]")
print(f"Total pages: {len(df)}")

# v3 vs CSV match
df['v3_match_csv'] = (df['v3_ai_value'] == df['csv_ai_value'])
v3_match_count = int(df['v3_match_csv'].sum())
print(f"v3 vs CSV match: {v3_match_count}/30 ({v3_match_count/30*100:.1f}%)")

# v22 vs CSV match
df['v22_match_csv'] = (df['v22_estimated_value'] == df['csv_ai_value'])
v22_match_count = int(df['v22_match_csv'].sum())
print(f"v22 vs CSV match: {v22_match_count}/30 ({v22_match_count/30*100:.1f}%)")

# Comparison categories
def categorize(row):
    v3_match = row['v3_match_csv']
    v22_match = row['v22_match_csv']
    
    if v3_match and v22_match:
        return 'both_match'
    elif v3_match and not v22_match:
        return 'v3_only_match'
    elif not v3_match and v22_match:
        return 'v22_only_match'
    else:
        v3_diff = abs(row['v3_ai_value'] - row['csv_ai_value']) if pd.notna(row['v3_ai_value']) else float('inf')
        v22_diff = abs(row['v22_estimated_value'] - row['csv_ai_value']) if pd.notna(row['v22_estimated_value']) else float('inf')
        if v22_diff < v3_diff:
            return 'both_mismatch_v22_closer'
        elif v3_diff < v22_diff:
            return 'both_mismatch_v3_closer'
        else:
            return 'both_mismatch_same_distance'

df['comparison_category'] = df.apply(categorize, axis=1)

print("\n[2. Comparison Categories]")
category_counts = df['comparison_category'].value_counts()
for cat, count in category_counts.items():
    pages = sorted(df[df['comparison_category'] == cat]['pdf_page_number'].tolist())
    print(f"{cat:30s}: {count:2d} pages {pages}")

# Improvement/Degradation
print("\n[3. Improvement/Degradation]")
improvement = df[df['comparison_category'].isin(['v22_only_match', 'both_mismatch_v22_closer'])]
improvement_pages = sorted(improvement['pdf_page_number'].tolist())
print(f"Improvement (v22 > v3): {len(improvement)} pages {improvement_pages}")

degradation = df[df['comparison_category'].isin(['v3_only_match', 'both_mismatch_v3_closer'])]
degradation_pages = sorted(degradation['pdf_page_number'].tolist())
print(f"Degradation (v22 < v3): {len(degradation)} pages {degradation_pages if degradation_pages else '(none)'}")

# Confidence
print("\n[4. Confidence Distribution]")
conf_counts = df['v22_confidence'].value_counts()
for conf, count in conf_counts.items():
    pages = sorted(df[df['v22_confidence'] == conf]['pdf_page_number'].tolist())
    print(f"confidence {conf:6s}: {count:2d} pages {pages}")

# Target cell found
print("\n[5. Target Cell Found]")
target_found = int(df['v22_target_cell_found'].sum())
print(f"target_cell_found = Yes: {target_found}/30 ({target_found/30*100:.1f}%)")

# Auto confirm and review required
print("\n[6. auto_confirm_candidate and review_required]")

def check_auto_confirm(row):
    if not row['v22_target_cell_found']:
        return False
    if pd.isna(row['v22_estimated_value']):
        return False
    if row['v22_confidence'] not in ['medium', 'high']:
        return False
    if row['v22_estimated_value'] != row['csv_ai_value']:
        return False
    if row['v22_visible_mark_type'] not in ['tally', 'digit', 'blank']:
        return False
    if row['review_required']:
        return False
    return True

df['auto_confirm_final'] = df.apply(check_auto_confirm, axis=1)
auto_count = int(df['auto_confirm_final'].sum())
auto_pages = sorted(df[df['auto_confirm_final']]['pdf_page_number'].tolist())
print(f"auto_confirm_candidate (recalculated): {auto_count} pages {auto_pages}")

def check_review(row):
    if not row['v22_target_cell_found']:
        return True
    if pd.isna(row['v22_estimated_value']):
        return True
    if row['v22_confidence'] == 'low':
        return True
    if row['v22_estimated_value'] != row['csv_ai_value']:
        return True
    if row['v22_visible_mark_type'] in ['unclear', 'unknown']:
        return True
    if row['v22_visible_mark_type'] == 'blank' and row['csv_ai_value'] > 0:
        return True
    v2_v3_diff = abs(row['v22_estimated_value'] - row['v3_ai_value']) if pd.notna(row['v3_ai_value']) else 0
    if v2_v3_diff > 2:
        return True
    return False

df['review_final'] = df.apply(check_review, axis=1)
review_count = int(df['review_final'].sum())
review_pages = sorted(df[df['review_final']]['pdf_page_number'].tolist())
print(f"review_required (recalculated): {review_count} pages {review_pages}")

# Exclusivity
overlap = int((df['auto_confirm_final'] & df['review_final']).sum())
print(f"Overlap (conflict): {overlap} pages")

# AI FLAG
print("\n[7. AI FLAG 13 Recount]")
ai_flag_list = [14, 11, 24, 12, 28, 2, 10, 15, 16, 20, 29, 9, 30]
ai_flag_df = df[df['pdf_page_number'].isin(ai_flag_list)].copy()

def flag_status(row):
    v3_match = row['v3_match_csv']
    v22_match = row['v22_match_csv']
    if not v3_match and v22_match:
        return 'resolved'
    elif v3_match and not v22_match:
        return 'new_issue'
    elif not v3_match and not v22_match:
        return 'still_flagged'
    else:
        return 'both_match'

ai_flag_df['ai_flag_status'] = ai_flag_df.apply(flag_status, axis=1)

resolved = int((ai_flag_df['ai_flag_status'] == 'resolved').sum())
still = int((ai_flag_df['ai_flag_status'] == 'still_flagged').sum())
new = int((ai_flag_df['ai_flag_status'] == 'new_issue').sum())

print(f"AI FLAG 13 resolved by v22: {resolved} pages")
print(f"AI FLAG still flagged: {still} pages")
print(f"AI FLAG new issues: {new} pages")
remaining = still + new
print(f"AI FLAG final: 13 -> {remaining} (reduction: {13-remaining})")

# Save
print("\n[8. Saving output files]")
detail_df = df[['pdf_page_number', 'store_name', 'v3_ai_value', 'v22_estimated_value', 'csv_ai_value', 
                 'v3_match_csv', 'v22_match_csv', 'comparison_category', 'v22_confidence', 
                 'v22_target_cell_found', 'v22_visible_mark_type', 'auto_confirm_final', 'review_final']]
detail_df.columns = ['page', 'store_name', 'v3_ai_value', 'v22_estimated_value', 'csv_ai_value',
                     'v3_match_csv', 'v22_match_csv', 'comparison_category', 'confidence',
                     'target_cell_found', 'visible_mark_type', 'auto_confirm_candidate_final', 'review_required_final']

detail_csv = OUTPUT_DIR / "phase6b_ai_tally_v22_all30_final_classification.csv"
detail_df.to_csv(detail_csv, index=False, encoding='utf-8-sig')
print(f"Saved: {detail_csv}")

ai_flag_detail = ai_flag_df[['pdf_page_number', 'store_name', 'v3_ai_value', 'v22_estimated_value', 'csv_ai_value',
                               'v3_status', 'v3_match_csv', 'v22_match_csv', 'ai_flag_status', 'v22_confidence']]
ai_flag_detail.columns = ['page', 'store_name', 'v3_ai_value', 'v22_estimated_value', 'csv_ai_value',
                          'v3_status', 'v3_match_csv', 'v22_match_csv', 'ai_flag_status', 'v22_confidence']

ai_flag_csv = OUTPUT_DIR / "phase6b_ai_tally_v22_ai_flag_13_reaudit.csv"
ai_flag_detail.to_csv(ai_flag_csv, index=False, encoding='utf-8-sig')
print(f"Saved: {ai_flag_csv}")

# Final summary
print("\n" + "=" * 80)
print("FINAL CONFIRMED METRICS")
print("=" * 80)
print(f"v3 vs CSV match:          {v3_match_count}/30 ({v3_match_count/30*100:.1f}%)")
print(f"v22 vs CSV match:         {v22_match_count}/30 ({v22_match_count/30*100:.1f}%)")
print(f"Improvement:              {len(improvement)} pages {improvement_pages}")
print(f"Degradation:              {len(degradation)} pages {degradation_pages if degradation_pages else '(none)'}")
print(f"\nauto_confirm_candidate:   {auto_count} pages ({auto_count/30*100:.1f}%)")
print(f"review_required:          {review_count} pages ({review_count/30*100:.1f}%)")
print(f"Overlap (conflict):       {overlap} pages")
print(f"\nAI FLAG change:           13 -> {remaining} (reduction: {13-remaining})")

# Judgment
if v22_match_count >= 27 and auto_count >= 21 and len(degradation) == 0:
    judgment = "A"
elif v22_match_count >= 15 and auto_count >= 12 and len(improvement) > 0:
    judgment = "B"
else:
    judgment = "C"

print(f"\nFinal Judgment: {judgment}")
print("=" * 80)

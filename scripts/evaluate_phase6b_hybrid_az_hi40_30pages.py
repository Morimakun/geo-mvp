"""
Phase 6B: Hybrid AZ + HI=40 30-Page Full Evaluation

目的:
  v3を標準版としつつ、既存の7ページv5テスト結果を使ってAZハイブリッドを
  全30ページで評価し、HI=40後処理を適用した最終数字を確定。

実装:
  1. v3 30ページ結果を読み込み
  2. 既存の7ページv5結果をマージ
  3. AZハイブリッドロジックを適用
  4. HI=40後処理を適用
  5. v3単独との比較

出力:
  - phase6b_hybrid_az_hi40_30pages_summary.csv
  - phase6b_hybrid_az_hi40_30pages_field_comparisons.csv
  - phase6b_hybrid_az_hi40_30pages_mismatch_list.csv
  - phase6b_hybrid_az_hi40_30pages_az_decisions.csv
  - レポートファイル
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "test_outputs"
V3_RECON_CSV = OUTPUT_DIR / "phase6b_v3_reconciliation_field_comparisons.csv"
V3_DETAILS_CSV = OUTPUT_DIR / "phase6b_30pages_extraction_details_v3.csv"
V5_TESTDATA_CSV = OUTPUT_DIR / "phase6b_v5_case_items_split_test_fixed.csv"

print("=" * 100)
print("Phase 6B: Full 30-Page Evaluation with AZ Hybrid + HI=40 Postprocessing")
print("=" * 100)
print()

# === Load v3 Data ===
print("Loading v3 baseline data...")
df_v3_details = pd.read_csv(V3_DETAILS_CSV)
df_v3_recon = pd.read_csv(V3_RECON_CSV)
df_v3_recon.columns = [c.lstrip('﻿') for c in df_v3_recon.columns]

print(f"  v3 details: {len(df_v3_details)} rows")
print(f"  v3 reconciliation: {len(df_v3_recon)} rows")
print()

# === Load v5 Test Data (7 pages) ===
print("Loading v5 test data (7 pages)...")
df_v5_test = pd.read_csv(V5_TESTDATA_CSV)
print(f"  v5 test data: {len(df_v5_test)} rows")
print()

# === Extract AZ from v3 (30 pages) ===
print("Extracting AZ values from v3...")
df_v3_az = df_v3_details[(df_v3_details['region'] == 'case_items') &
                         (df_v3_details['item'] == 'AZ')].copy()
df_v3_az = df_v3_az.rename(columns={'page': 'page_index', 'item': 'field_code', 'value': 'v3_value'})
df_v3_az = df_v3_az[['page_index', 'v3_value']]
print(f"  AZ rows in v3: {len(df_v3_az)}")
print()

# === Extract v5 AZ (7 pages) ===
print("Extracting v5 AZ results...")
df_v5_az = df_v5_test[df_v5_test['field_code'] == 'AZ'].copy()
df_v5_az = df_v5_az[['page_index', 'v5_value']]
print(f"  v5 AZ rows: {len(df_v5_az)}")
print()

# === Merge v3 and v5 ===
print("Merging v3 and v5 results...")
df_az_all = pd.merge(
    df_v3_az,
    df_v5_az,
    on='page_index',
    how='left'
)
print(f"  Merged: {len(df_az_all)} rows (7 pages have v5, 23 pages v3 only)")
print()

# === Apply Hybrid Logic ===
print("Applying AZ hybrid logic...")
def hybrid_az(row):
    v3_val = row['v3_value']
    v5_val = row['v5_value']

    v3_is_null = pd.isna(v3_val) or str(v3_val).lower() in ['nan', '']
    v3_is_zero = (not v3_is_null) and (v3_val == 0 or v3_val == 0.0 or str(v3_val) == '0')
    v5_is_null = pd.isna(v5_val) or str(v5_val).lower() in ['nan', '']
    v5_is_zero = (not v5_is_null) and (v5_val == 0 or v5_val == 0.0)

    if not v5_is_null and not v5_is_zero:
        return pd.Series({'final_AZ': v5_val, 'az_source': 'v5'})
    elif v5_is_zero and not v3_is_null and not v3_is_zero:
        return pd.Series({'final_AZ': v3_val, 'az_source': 'v3_fallback'})
    elif v5_is_zero and (v3_is_null or v3_is_zero):
        return pd.Series({'final_AZ': 0, 'az_source': 'v5_zero_kept'})
    elif v5_is_null:
        return pd.Series({'final_AZ': v3_val if not v3_is_null else None, 'az_source': 'v3_default'})
    else:
        return pd.Series({'final_AZ': v3_val if not v3_is_null else None, 'az_source': 'v3_default'})

az_logic = df_az_all.apply(hybrid_az, axis=1)
df_az_all = pd.concat([df_az_all.reset_index(drop=True), az_logic.reset_index(drop=True)], axis=1)

az_v5_count = (df_az_all['az_source'] == 'v5').sum()
az_fallback_count = (df_az_all['az_source'] == 'v3_fallback').sum()
az_zero_count = (df_az_all['az_source'] == 'v5_zero_kept').sum()
az_default_count = (df_az_all['az_source'] == 'v3_default').sum()

print(f"  v5 adopted: {az_v5_count}")
print(f"  v3 fallback (実績保護): {az_fallback_count}")
print(f"  v5 zero kept (集計0部分): {az_zero_count}")
print(f"  v3 default (v5 null時): {az_default_count}")
print()

# === Prepare Hybrid Reconciliation Data ===
print("Preparing hybrid reconciliation data...")
df_hybrid = df_v3_recon.copy()

# Replace AZ values with hybrid results
az_map = dict(zip(df_az_all['page_index'], df_az_all['final_AZ']))
for idx, row in df_hybrid[df_hybrid['csv_column_code'] == 'AZ'].iterrows():
    page_num = row['page_number']
    if page_num in az_map:
        new_val = az_map[page_num]
        # Convert to string to match csv column type
        new_str = str(new_val) if pd.notna(new_val) else ''
        df_hybrid.at[idx, 'pdf_value'] = new_str

# Apply HI=40 postprocessing
mask_hi40 = (df_hybrid['csv_column_code'] == 'HI') & (df_hybrid['pdf_value'].astype(str) == '40')
hi40_count = mask_hi40.sum()
df_hybrid.loc[mask_hi40, 'pdf_value'] = 'uncertain'
df_hybrid.loc[mask_hi40, 'comparison_status'] = 'skipped_pdf_uncertain'
df_hybrid.loc[mask_hi40, 'reason'] = 'PDF value is uncertain (template misread HI=40)'

print(f"  HI=40 postprocessed: {hi40_count} rows")
print()

# === Recalculate Comparisons ===
print("Recalculating comparisons...")
def recalc_status(row):
    pdf_v = row['pdf_value']
    csv_v = row['csv_value']

    pdf_str = str(pdf_v).lower() if pd.notna(pdf_v) else ''
    csv_str = str(csv_v).lower() if pd.notna(csv_v) else ''

    if pdf_str == 'uncertain':
        return 'skipped_pdf_uncertain'
    pdf_null = pd.isna(pdf_v) or pdf_str in ['nan', '']
    csv_null = pd.isna(csv_v) or csv_str in ['nan', '']

    if pdf_null and csv_null:
        return 'skipped_both_null'
    if pdf_null:
        return 'skipped_pdf_null'
    if csv_null:
        return 'skipped_csv_null'

    try:
        if float(pdf_v) == float(csv_v):
            return 'match'
        else:
            return 'mismatch'
    except:
        if str(pdf_v) == str(csv_v):
            return 'match'
        return 'mismatch'

df_hybrid['comparison_status_new'] = df_hybrid.apply(recalc_status, axis=1)

# === Calculate Summary ===
print("Calculating summary...")
v3_match = (df_v3_recon['comparison_status'] == 'match').sum()
v3_mismatch = (df_v3_recon['comparison_status'] == 'mismatch').sum()
v3_total = v3_match + v3_mismatch
v3_rate = v3_match / v3_total * 100 if v3_total > 0 else 0

hybrid_match = (df_hybrid['comparison_status_new'] == 'match').sum()
hybrid_mismatch = (df_hybrid['comparison_status_new'] == 'mismatch').sum()
hybrid_total = hybrid_match + hybrid_mismatch
hybrid_rate = hybrid_match / hybrid_total * 100 if hybrid_total > 0 else 0

print()
print(f"v3 baseline (30 pages all items):")
print(f"  match: {v3_match}, mismatch: {v3_mismatch}, total: {v3_total}")
print(f"  match_rate: {v3_rate:.1f}%")
print()
print(f"Hybrid (AZ ハイブリッド + HI=40 review化):")
print(f"  match: {hybrid_match}, mismatch: {hybrid_mismatch}, total: {hybrid_total}")
print(f"  match_rate: {hybrid_rate:.1f}%")
print()
print(f"Changes:")
print(f"  match Δ: {hybrid_match - v3_match:+d}")
print(f"  mismatch Δ: {hybrid_mismatch - v3_mismatch:+d}")
print(f"  match_rate Δ: {hybrid_rate - v3_rate:+.1f}pt")
print(f"  HI=40 review化: {hi40_count}")
print()

# === Save Outputs ===
print("Saving outputs...")

# Summary CSV
summary_data = {
    'metric': [
        'v3_match', 'v3_mismatch', 'v3_total_compared', 'v3_match_rate',
        'hybrid_match', 'hybrid_mismatch', 'hybrid_total_compared', 'hybrid_match_rate',
        'match_delta', 'mismatch_delta', 'match_rate_delta_pt',
        'az_v5_adopted', 'az_v3_fallback', 'az_v5_zero_kept', 'az_v3_default',
        'hi40_reviewed'
    ],
    'value': [
        v3_match, v3_mismatch, v3_total, f'{v3_rate:.1f}%',
        hybrid_match, hybrid_mismatch, hybrid_total, f'{hybrid_rate:.1f}%',
        hybrid_match - v3_match, hybrid_mismatch - v3_mismatch, f'{hybrid_rate - v3_rate:+.1f}',
        az_v5_count, az_fallback_count, az_zero_count, az_default_count,
        hi40_count
    ]
}
pd.DataFrame(summary_data).to_csv(
    OUTPUT_DIR / "phase6b_hybrid_az_hi40_30pages_summary.csv",
    index=False, encoding='utf-8-sig'
)

# Field comparisons
df_hybrid.to_csv(
    OUTPUT_DIR / "phase6b_hybrid_az_hi40_30pages_field_comparisons.csv",
    index=False, encoding='utf-8-sig'
)

# Mismatch list
mismatch_list = df_hybrid[df_hybrid['comparison_status_new'] == 'mismatch'].copy()
mismatch_list.to_csv(
    OUTPUT_DIR / "phase6b_hybrid_az_hi40_30pages_mismatch_list.csv",
    index=False, encoding='utf-8-sig'
)

# AZ decisions
az_decisions = df_az_all.copy()
az_decisions.to_csv(
    OUTPUT_DIR / "phase6b_hybrid_az_hi40_30pages_az_decisions.csv",
    index=False, encoding='utf-8-sig'
)

print("  Summary: phase6b_hybrid_az_hi40_30pages_summary.csv")
print("  Field comparisons: phase6b_hybrid_az_hi40_30pages_field_comparisons.csv")
print("  Mismatch list: phase6b_hybrid_az_hi40_30pages_mismatch_list.csv")
print("  AZ decisions: phase6b_hybrid_az_hi40_30pages_az_decisions.csv")
print()

print("=" * 100)
print("Evaluation complete.")
print("=" * 100)

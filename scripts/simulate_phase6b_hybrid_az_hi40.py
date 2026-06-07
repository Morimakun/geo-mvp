"""
Phase 6B Hybrid AZ + HI=40 Postprocessing Simulation

目的:
  既存のv3/v5/v5.2出力CSVを使い、以下2つの後処理をシミュレーション。
  Vision API を新規実行しない、既存ファイルからの加工のみ。

  1. AZ ハイブリッド判定:
       v5_AZ != null and != 0  → use v5
       v5_AZ == 0 and v3 has value → use v3 (実績喪失防止)
       v5_AZ == 0 and v3 also null/0 → keep 0 (集計0部分として保持)
       v5_AZ is null → use v3 (default)

  2. HI=40 後処理:
       HI == 40 → uncertain (template misread として review 化)

出力:
  data/test_outputs/phase6b_hybrid_az_hi40_simulation.csv
  data/test_outputs/phase6b_hybrid_az_hi40_summary.csv
"""

import sys
from pathlib import Path
import pandas as pd

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs"

# === Input files ===
v3_recon_csv = OUTPUT_DIR / "phase6b_v3_reconciliation_field_comparisons.csv"
v3_details_csv = OUTPUT_DIR / "phase6b_30pages_extraction_details_v3.csv"
v5_csv = OUTPUT_DIR / "phase6b_v5_case_items_split_test_fixed.csv"

TEST_PAGE_INDICES = [0, 5, 7, 8, 9, 14, 27]

print("=" * 100)
print("Phase 6B: Hybrid AZ + HI=40 Postprocessing Simulation")
print("=" * 100)
print()

# === Load v3 reconciliation comparisons ===
df_v3 = pd.read_csv(v3_recon_csv)
df_v3.columns = [c.lstrip('﻿') for c in df_v3.columns]
print(f"v3 reconciliation rows: {len(df_v3)}")

# === Load v5 case_items split test ===
df_v5 = pd.read_csv(v5_csv)
print(f"v5 split test rows: {len(df_v5)}")
print()

# ====================================================================
# Part 1: AZ Hybrid Simulation
# ====================================================================
print("-" * 100)
print("Part 1: AZ Hybrid Simulation (7 test pages)")
print("-" * 100)
print()

# Extract AZ rows from v3 reconciliation for test pages
df_v3_az = df_v3[
    (df_v3['csv_column_code'] == 'AZ') &
    (df_v3['page_number'].isin(TEST_PAGE_INDICES))
].copy()

# Extract AZ from v5
df_v5_az = df_v5[df_v5['field_code'] == 'AZ'].copy()
df_v5_az = df_v5_az[['page_index', 'v5_value']].rename(columns={'page_index': 'page_number'})

# Merge
df_az = pd.merge(df_v3_az, df_v5_az, on='page_number', how='left')

# Apply hybrid logic
def hybrid_az(row):
    v3_val = row['pdf_value']
    v5_val = row['v5_value']

    v3_is_null = pd.isna(v3_val) or v3_val == '' or str(v3_val).lower() == 'nan'
    v3_is_zero = str(v3_val) == '0' or v3_val == 0 or v3_val == 0.0
    v5_is_null = pd.isna(v5_val)
    v5_is_zero = v5_val == 0 or v5_val == 0.0

    if not v5_is_null and not v5_is_zero:
        return pd.Series({'final_AZ': v5_val, 'az_source': 'v5', 'az_review_reason': ''})
    elif v5_is_zero and not v3_is_null and not v3_is_zero:
        return pd.Series({'final_AZ': v3_val, 'az_source': 'v3_fallback',
                          'az_review_reason': 'v5_zero_but_v3_has_value'})
    elif v5_is_zero and (v3_is_null or v3_is_zero):
        return pd.Series({'final_AZ': 0, 'az_source': 'v5_zero_kept', 'az_review_reason': ''})
    else:
        # v5 is null
        return pd.Series({'final_AZ': v3_val if not v3_is_null else None,
                          'az_source': 'v3_default', 'az_review_reason': ''})

az_results = df_az.apply(hybrid_az, axis=1)
df_az = pd.concat([df_az.reset_index(drop=True), az_results.reset_index(drop=True)], axis=1)

# Re-compare with CSV value
def new_comparison(row):
    final = row['final_AZ']
    csv_v = row['csv_value']
    final_is_null = pd.isna(final) or final == '' or str(final).lower() == 'nan'
    csv_is_null = pd.isna(csv_v) or csv_v == '' or str(csv_v).lower() == 'nan'

    if row['az_review_reason']:
        return 'review_required'
    if final_is_null and csv_is_null:
        return 'skipped_both_null'
    if final_is_null:
        return 'skipped_pdf_null'
    if csv_is_null:
        return 'skipped_csv_null'
    try:
        if float(final) == float(csv_v):
            return 'match'
        else:
            return 'mismatch'
    except (ValueError, TypeError):
        return str(final) == str(csv_v) and 'match' or 'mismatch'

df_az['new_status'] = df_az.apply(new_comparison, axis=1)

# Print AZ result table
print(f"{'page':<5} {'v3':<10} {'v5':<8} {'csv':<8} {'final':<10} {'source':<18} {'old_status':<22} {'new_status':<20}")
for _, row in df_az.iterrows():
    print(f"P{int(row['page_number'])+1:02d}   "
          f"{str(row['pdf_value']):<10} {str(row['v5_value']):<8} "
          f"{str(row['csv_value']):<8} {str(row['final_AZ']):<10} "
          f"{row['az_source']:<18} {row['comparison_status']:<22} {row['new_status']:<20}")
print()

# Summarize AZ
az_v5_adopted = (df_az['az_source'] == 'v5').sum()
az_v3_fallback = (df_az['az_source'] == 'v3_fallback').sum()
az_v5_zero_kept = (df_az['az_source'] == 'v5_zero_kept').sum()
az_v3_default = (df_az['az_source'] == 'v3_default').sum()

old_mismatch = (df_az['comparison_status'] == 'mismatch').sum()
old_match = (df_az['comparison_status'] == 'match').sum()
new_mismatch = (df_az['new_status'] == 'mismatch').sum()
new_match = (df_az['new_status'] == 'match').sum()
new_review = (df_az['new_status'] == 'review_required').sum()

print(f"AZ Source breakdown:")
print(f"  v5 adopted (改善取り込み):  {az_v5_adopted}")
print(f"  v3 fallback (実績保護):    {az_v3_fallback}")
print(f"  v5 zero kept (集計0部分):  {az_v5_zero_kept}")
print(f"  v3 default (v5 null時):    {az_v3_default}")
print()
print(f"AZ Status change:")
print(f"  match:    {old_match} → {new_match}")
print(f"  mismatch: {old_mismatch} → {new_mismatch}")
print(f"  review:   0 → {new_review}")
print()

# ====================================================================
# Part 2: HI=40 Postprocessing Simulation
# ====================================================================
print("-" * 100)
print("Part 2: HI=40 Postprocessing Simulation (all 30 pages)")
print("-" * 100)
print()

df_hi = df_v3[df_v3['csv_column_code'] == 'HI'].copy()
df_hi40 = df_hi[df_hi['pdf_value'].astype(str) == '40'].copy()

print(f"HI=40 occurrences found: {len(df_hi40)}")
print()

if len(df_hi40) > 0:
    for _, row in df_hi40.iterrows():
        print(f"  P{int(row['page_number'])+1:02d}: PDF={row['pdf_value']}, "
              f"CSV={row['csv_value']}, old_status={row['comparison_status']}")

    # Apply postprocessing
    df_hi40['new_pdf_value'] = 'uncertain'
    df_hi40['new_status'] = 'skipped_pdf_uncertain'
    df_hi40['hi_review_reason'] = 'possible_template_40_misread'

    hi40_mismatch_before = (df_hi40['comparison_status'] == 'mismatch').sum()
    hi40_mismatch_after = (df_hi40['new_status'] == 'mismatch').sum()
    print()
    print(f"HI=40 Status change:")
    print(f"  mismatch: {hi40_mismatch_before} → {hi40_mismatch_after}")
    print(f"  review:   0 → {len(df_hi40)}")
else:
    print("  No HI=40 found")
print()

# ====================================================================
# Part 3: Overall Impact Estimation
# ====================================================================
print("-" * 100)
print("Part 3: Overall Impact (v3 baseline → hybrid simulation)")
print("-" * 100)
print()

# v3 全体集計
v3_total_mismatch = (df_v3['comparison_status'] == 'mismatch').sum()
v3_total_match = (df_v3['comparison_status'] == 'match').sum()
v3_total_compared = v3_total_mismatch + v3_total_match
v3_match_rate = v3_total_match / v3_total_compared * 100 if v3_total_compared > 0 else 0

print(f"v3 baseline (全30ページ全項目):")
print(f"  比較実施: {v3_total_compared}")
print(f"  match:    {v3_total_match}")
print(f"  mismatch: {v3_total_mismatch}")
print(f"  match_rate: {v3_match_rate:.1f}%")
print()

# Hybrid simulation delta (test 7 pages のみで AZ + HI=40 後処理)
az_delta_match = new_match - old_match
az_delta_mismatch = new_mismatch - old_mismatch
hi_delta_mismatch = -len(df_hi40)

projected_match = v3_total_match + az_delta_match
projected_mismatch = v3_total_mismatch + az_delta_mismatch + hi_delta_mismatch
projected_compared = projected_match + projected_mismatch
projected_rate = projected_match / projected_compared * 100 if projected_compared > 0 else 0

print(f"Simulation delta:")
print(f"  AZ Δmatch:    {az_delta_match:+d} (7 pages only)")
print(f"  AZ Δmismatch: {az_delta_mismatch:+d} (7 pages only)")
print(f"  HI Δmismatch: {hi_delta_mismatch:+d} (HI=40 review化)")
print()
print(f"Projected after postprocess (7P AZ + 全30P HI):")
print(f"  match:    {projected_match}")
print(f"  mismatch: {projected_mismatch}")
print(f"  match_rate: {projected_rate:.1f}% (v3 {v3_match_rate:.1f}% から {projected_rate - v3_match_rate:+.1f}pt)")
print()

# ====================================================================
# Save outputs
# ====================================================================
print("-" * 100)
print("Saving outputs")
print("-" * 100)

# Detailed simulation CSV
sim_csv = OUTPUT_DIR / "phase6b_hybrid_az_hi40_simulation.csv"
df_az_export = df_az[[
    'page_number', 'mapped_store_code', 'pdf_value', 'v5_value', 'csv_value',
    'final_AZ', 'az_source', 'az_review_reason',
    'comparison_status', 'new_status'
]].copy()
df_az_export['rule_type'] = 'AZ_hybrid'

if len(df_hi40) > 0:
    df_hi40_export = df_hi40[[
        'page_number', 'mapped_store_code', 'pdf_value', 'csv_value',
        'new_pdf_value', 'new_status', 'hi_review_reason', 'comparison_status'
    ]].copy()
    df_hi40_export['rule_type'] = 'HI40_postprocess'
    # Combine
    combined = pd.concat([df_az_export, df_hi40_export], ignore_index=True, sort=False)
else:
    combined = df_az_export

combined.to_csv(sim_csv, index=False, encoding='utf-8-sig')
print(f"  Detailed: {sim_csv}")

# Summary CSV
summary_data = [
    {'metric': 'AZ v5 adopted', 'value': az_v5_adopted, 'note': '改善取り込み'},
    {'metric': 'AZ v3 fallback', 'value': az_v3_fallback, 'note': '実績保護(P15型)'},
    {'metric': 'AZ v5 zero kept', 'value': az_v5_zero_kept, 'note': '集計0部分として保持'},
    {'metric': 'AZ v3 default', 'value': az_v3_default, 'note': 'v5 null時'},
    {'metric': 'AZ match (before→after)', 'value': f'{old_match}→{new_match}', 'note': ''},
    {'metric': 'AZ mismatch (before→after)', 'value': f'{old_mismatch}→{new_mismatch}', 'note': ''},
    {'metric': 'AZ review_required', 'value': new_review, 'note': '手動確認推奨'},
    {'metric': 'HI=40 detected', 'value': len(df_hi40), 'note': 'テンプレート誤読'},
    {'metric': 'HI=40 review化', 'value': len(df_hi40), 'note': 'mismatch から除外'},
    {'metric': 'v3 match_rate (baseline)', 'value': f'{v3_match_rate:.1f}%', 'note': ''},
    {'metric': 'projected match_rate', 'value': f'{projected_rate:.1f}%', 'note': f'{projected_rate - v3_match_rate:+.1f}pt'},
]
summary_csv = OUTPUT_DIR / "phase6b_hybrid_az_hi40_summary.csv"
pd.DataFrame(summary_data).to_csv(summary_csv, index=False, encoding='utf-8-sig')
print(f"  Summary:  {summary_csv}")

print()
print("=" * 100)
print("Simulation complete.")
print("=" * 100)

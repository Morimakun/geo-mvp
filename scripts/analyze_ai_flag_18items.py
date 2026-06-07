"""
Phase 6B: AI (Total) 18 FLAG Analysis

目的：
  AI（合計欄）の18件mismatchを分析し、原因を分類する。
  PDF抽出は100%成功だが、Salesforce値と食い違う可能性を調査。

既存CSVのみ、新規実行なし。
"""

import sys
from pathlib import Path
import pandas as pd

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs"
V3_CSV = OUTPUT_DIR / "phase6b_v3_reconciliation_field_comparisons.csv"

print("=" * 120)
print("Phase 6B: AI (Total) FLAG 分析")
print("=" * 120)
print()

# Load v3
df = pd.read_csv(V3_CSV, dtype=str)
df.columns = [c.lstrip('﻿') for c in df.columns]

# Filter AI rows
df_ai = df[df['csv_column_code'] == 'AI'].copy()
print(f"Total AI rows: {len(df_ai)}")
print()

# Categorize status
df_ai['flag_type'] = df_ai['comparison_status'].apply(
    lambda s: 'mismatch' if s == 'mismatch' else
              'csv_error' if s == 'skipped_csv_null' else
              'pdf_null' if s == 'skipped_pdf_null' else
              'match'
)

summary = df_ai['flag_type'].value_counts()
print(f"Status breakdown:")
for status, count in summary.items():
    print(f"  {status}: {count}")
print()

# Focus on mismatch (18 items)
df_mismatch = df_ai[df_ai['flag_type'] == 'mismatch'].copy()
print(f"Mismatch items: {len(df_mismatch)}")
print()

# Detailed view
print("-" * 120)
print("AI Mismatch 詳細一覧")
print("-" * 120)
print()

for idx, row in df_mismatch.iterrows():
    pdf_v = row.get('pdf_value')
    csv_v = row.get('csv_value')
    print(f"P{int(row['page_number'])+1:02d} {row['pdf_store_name']:<25} "
          f"PDF={str(pdf_v):<6} CSV={str(csv_v):<6} "
          f"reason={row.get('reason', '')}")

print()

# Calculate differences
df_mismatch['pdf_num'] = pd.to_numeric(df_mismatch['pdf_value'], errors='coerce')
df_mismatch['csv_num'] = pd.to_numeric(df_mismatch['csv_value'], errors='coerce')
df_mismatch['diff'] = df_mismatch['csv_num'] - df_mismatch['pdf_num']
df_mismatch['diff_abs'] = df_mismatch['diff'].abs()

print("-" * 120)
print("差分ランキング（大きい順）")
print("-" * 120)
print()

df_mismatch_sorted = df_mismatch.sort_values('diff_abs', ascending=False)
for idx, row in df_mismatch_sorted.iterrows():
    diff = row['diff']
    print(f"P{int(row['page_number'])+1:02d} {row['pdf_store_name']:<25} "
          f"PDF={int(row['pdf_num']) if pd.notna(row['pdf_num']) else 'null'}  "
          f"CSV={int(row['csv_num']) if pd.notna(row['csv_num']) else 'null'}  "
          f"差分={diff:+.0f}")

print()

# CSV column info
print("-" * 120)
print("CSV列定義情報")
print("-" * 120)
print()

ai_csv_col = df_ai.iloc[0]['csv_column_code']
ai_csv_name = df_ai.iloc[0]['csv_column_name']
ai_csv_num = df_ai.iloc[0]['csv_column_number'] if 'csv_column_number' in df_ai.columns else 'N/A'

print(f"csv_column_code: {ai_csv_col}")
print(f"csv_column_name: {ai_csv_name}")
print(f"csv_column_number: {ai_csv_num}")
print()

# Look for internal columns related
print("AI関連の他の項目:")
for code in ['AU', 'AV', 'AY', 'AZ']:
    au_rows = df[df['csv_column_code'] == code]
    if len(au_rows) > 0:
        print(f"  {code}: {au_rows.iloc[0].get('csv_column_name')} (col_num={au_rows.iloc[0].get('csv_column_number')})")

print()

# PDF vs CSV type analysis
print("-" * 120)
print("差分パターン分析")
print("-" * 120)
print()

# PDF=0 vs CSV>0 pattern
pdf_zero = df_mismatch[df_mismatch['pdf_num'] == 0]
print(f"Pattern: PDF=0, CSV>0: {len(pdf_zero)} items")
for idx, row in pdf_zero.iterrows():
    print(f"  P{int(row['page_number'])+1:02d} PDF={int(row['pdf_num'])} CSV={int(row['csv_num'])} (Δ={int(row['diff'])})")

print()

# PDF>0 vs CSV different
pdf_nonzero = df_mismatch[df_mismatch['pdf_num'] > 0]
print(f"Pattern: PDF>0, CSV≠PDF: {len(pdf_nonzero)} items")
for idx, row in pdf_nonzero.iterrows():
    print(f"  P{int(row['page_number'])+1:02d} PDF={int(row['pdf_num'])} CSV={int(row['csv_num'])} (Δ={int(row['diff'])})")

print()

# CSV error rows
df_csv_err = df_ai[df_ai['flag_type'] == 'csv_error'].copy()
if len(df_csv_err) > 0:
    print(f"-" * 120)
    print(f"CSV列アクセスエラー: {len(df_csv_err)} items")
    print(f"-" * 120)
    print()
    for idx, row in df_csv_err.iterrows():
        print(f"P{int(row['page_number'])+1:02d} {row['pdf_store_name']:<25} "
              f"PDF={str(row.get('pdf_value')):<6} reason: CSV column access error")
    print()

# PDF null rows
df_pdf_null = df_ai[df_ai['flag_type'] == 'pdf_null'].copy()
if len(df_pdf_null) > 0:
    print(f"-" * 120)
    print(f"PDF値なし: {len(df_pdf_null)} items")
    print(f"-" * 120)
    print()
    for idx, row in df_pdf_null.iterrows():
        print(f"P{int(row['page_number'])+1:02d} {row['pdf_store_name']:<25} CSV={str(row.get('csv_value')):<6}")
    print()

# Match rows
df_match = df_ai[df_ai['flag_type'] == 'match'].copy()
print(f"-" * 120)
print(f"一致行: {len(df_match)} items")
print(f"-" * 120)
print()

# Save analysis
print("Saving outputs...")

# Mismatch detail
df_mismatch_export = df_mismatch[[
    'page_number', 'pdf_store_name', 'mapped_store_code',
    'pdf_value', 'csv_value', 'diff', 'diff_abs', 'reason'
]].copy()
df_mismatch_export.columns = [
    'page_index', 'store_name', 'store_code', 'pdf_value', 'csv_value',
    'difference', 'diff_abs', 'reason'
]
df_mismatch_export = df_mismatch_export.sort_values('diff_abs', ascending=False)
df_mismatch_export.to_csv(
    OUTPUT_DIR / "phase6b_ai_flag_analysis.csv",
    index=False, encoding='utf-8-sig'
)
print(f"  Saved: phase6b_ai_flag_analysis.csv")
print()

print("=" * 120)
print("AI FLAG分析完了")
print("=" * 120)

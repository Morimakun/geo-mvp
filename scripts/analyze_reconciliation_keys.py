#!/usr/bin/env python3
"""
リアルデータ × マスタデータ 照合キー検証スクリプト
目的: CSV/PDF と店舗・スタッフマスタの対応を検証
"""

import pandas as pd
import os
import unicodedata
import re
from pathlib import Path

# パス設定
PROJECT_ROOT = Path(__file__).parent.parent
CSV_FILE = PROJECT_ROOT / "tests/fixtures/geo_pdf_reconciliation/report1780043296399.csv"
STORE_MASTER = PROJECT_ROOT / "data/master/store_code_mapping.csv"
STAFF_MASTER = PROJECT_ROOT / "data/master/staff_name_master.csv"
OUTPUT_DIR = PROJECT_ROOT / "data/test_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

def normalize_text(text):
    """テキスト正規化: 全角→半角、空白削除、表記揺れ対応"""
    if pd.isna(text):
        return None
    text = str(text).strip()
    # 全角を半角へ
    text = unicodedata.normalize('NFKC', text)
    # 複数の空白を1つに
    text = re.sub(r'\s+', ' ', text)
    # 大文字小文字統一
    text = text.upper()
    return text

def main():
    print("=" * 80)
    print("リアルデータ × マスタデータ 照合キー分析")
    print("=" * 80)

    # 1. マスタデータ読込
    print("\n【Step 1】マスタデータ読込")
    store_master = pd.read_csv(STORE_MASTER)
    staff_master = pd.read_csv(STAFF_MASTER)

    print(f"  店舗マスタ: {len(store_master)}件")
    print(f"  スタッフマスタ: {len(staff_master)}名")

    # 店舗マスタを正規化
    store_master['store_code_normalized'] = store_master['store_code'].apply(normalize_text)
    store_master['store_name_normalized'] = store_master['store_name'].apply(normalize_text)

    # 2. CSVデータ読込
    print("\n【Step 2】CSVデータ読込")
    df_csv = pd.read_csv(CSV_FILE, encoding='cp932')
    print(f"  CSV: {len(df_csv)}行 × {len(df_csv.columns)}列")
    print(f"  対象日付: {df_csv.iloc[:, -1].unique()}")

    # 対象営業日のフィルタ（2026/05/17）
    target_date = '2026/05/17'
    df_target = df_csv[df_csv.iloc[:, -1] == target_date].copy()
    print(f"  対象営業日({target_date})の件数: {len(df_target)}")

    # 店舗コード列（列281）の確認
    store_code_col = df_csv.columns[280]  # 0-indexed, so 281 is [280]
    print(f"\n  店舗コード列({store_code_col})の値:")
    store_codes_csv = df_target.iloc[:, 280].value_counts()
    for code, count in store_codes_csv.head(10).items():
        print(f"    {code}: {count}件")

    # 3. 店舗マスタとの突合
    print("\n【Step 3】店舗マスタとの突合")
    store_match = 0
    store_nomatch = 0

    for code in df_target.iloc[:, 280].unique():
        if code in store_master['store_code'].values:
            store_match += 1
            store_info = store_master[store_master['store_code'] == code].iloc[0]
            print(f"  OK {code}: {store_info['store_name']} (NO:{store_info['store_no']})")
        else:
            store_nomatch += 1
            print(f"  NG {code}: Not in master")

    print(f"\n  一致: {store_match}件、未一致: {store_nomatch}件")

    # 4. 照合キー候補の評価
    print("\n【Step 4】照合キー候補の評価")

    # 候補A: 日付 + 店舗コード
    print("\n  候補A: 日付 + 店舗コード")
    key_a = df_target.groupby(df_target.iloc[:, 280]).size()
    print(f"    Uniqueness: {'Yes (1 per store)' if len(key_a) == len(df_target) else 'No (duplicates)'}")
    print(f"    重複パターン:")
    for store, count in key_a[key_a > 1].items():
        print(f"      {store}: {count}件")

    # 候補B: 日付 + 店舗NO（マスタとの結合）
    print("\n  候補B: 日付 + 店舗NO（マスタとの結合）")
    df_with_store_no = df_target.copy()
    df_with_store_no['store_no'] = df_with_store_no.iloc[:, 280].apply(
        lambda x: store_master[store_master['store_code'] == x]['store_no'].values[0]
        if x in store_master['store_code'].values else None
    )
    key_b = df_with_store_no.groupby('store_no').size()
    print(f"    Match rate: {(df_with_store_no['store_no'].notna().sum())} / {len(df_with_store_no)}")
    print(f"    重複パターン:")
    for no, count in key_b[key_b > 1].items():
        if pd.notna(no):
            print(f"      NO {no}: {count}件")

    # 5. CSV側のスタッフ情報確認
    print("\n【Step 5】CSV側のスタッフ情報確認")
    # スタッフ情報がある列を検索
    staff_cols_found = []
    for i, col in enumerate(df_csv.columns, 1):
        if any(x in col.lower() for x in ['staff', 'staff_no', '氏名', 'no']):
            staff_cols_found.append((i, col))

    if staff_cols_found:
        print(f"  スタッフ関連列({len(staff_cols_found)}個):")
        for col_num, col_name in staff_cols_found[:5]:
            print(f"    列{col_num}: {col_name}")
            sample_vals = df_target.iloc[:, col_num-1].dropna().unique()[:3]
            print(f"      例: {sample_vals}")
    else:
        print("  スタッフ関連列: 見つかりませんでした")

    # 6. 結果サマリーCSV作成
    print("\n【Step 6】検証結果CSV作成")

    result_df = pd.DataFrame({
        'row_num': range(1, len(df_target) + 1),
        'store_code': df_target.iloc[:, 280].values,
        'store_name': df_target.iloc[:, 280].apply(
            lambda x: store_master[store_master['store_code'] == x]['store_name'].values[0]
            if x in store_master['store_code'].values else 'NOT FOUND'
        ).values,
        'store_no': df_target.iloc[:, 280].apply(
            lambda x: store_master[store_master['store_code'] == x]['store_no'].values[0]
            if x in store_master['store_code'].values else None
        ).values,
    })

    output_csv = OUTPUT_DIR / "csv_store_master_match_20260604.csv"
    result_df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"  [OK] {output_csv}")

    # 7. 仮説検証
    print("\n【Step 7】仮説検証")
    print(f"  Hypothesis 1: CSV is store-daily data, PDF is partial stores")
    print(f"    > CSV 25 records for {len(store_master)} stores vs {len(key_a)} unique codes")
    print(f"  Hypothesis 2: CSV has multiple rows per staff")
    print(f"    > Need to verify CSV breakdown (waiting for staff column)")
    print(f"  Hypothesis 3: PDF 1 page = CSV multiple rows merged")
    print(f"    > Need PDF extraction validation")
    print(f"  Hypothesis 4: Actual key is date + store + staff")
    print(f"    > CSV staff column check is priority")

    print("\n" + "=" * 80)
    print("分析完了")
    print("=" * 80)

if __name__ == "__main__":
    main()

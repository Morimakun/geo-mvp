# -*- coding: utf-8 -*-
"""
Phase 2.5: Salesforce CSV全ヘッダー棚卸し＆PDF「AI合計欄」対応列候補抽出

目的:
    CSV全283列を棚卸しし、PDF目視「AI合計欄」に対応する列を推定する。
    API実行・Vision API実行なし。値の統計と一致率のみで判定。

出力:
    1. salesforce_csv_header_inventory.csv: 全列棚卸し
    2. ai_total_candidate_columns.csv: ヘッダー名から候補抽出
    3. ai_total_column_match_score_all_columns.csv: 全列スコアリング
    4. ai_total_top_candidate_column_comparison.csv: 上位候補と詳細比較
"""

import sys, io
from pathlib import Path
from collections import Counter
import pandas as pd
import numpy as np

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ============================================================
# 設定
# ============================================================

CSV_PATH = Path("~/Downloads/report1780043296399.csv").expanduser()
GT_PATH = Path("data/test_outputs/phase5_pdf_visual_accuracy_recount_detail_v2.csv")
OUTPUT_DIR = Path("data/test_outputs/csv_field_mapping_audit")

# PDF目視確認済みAI合計欄
PDF_VISUAL_AI_TOTAL = {
    "P14": 3, "P16": 9, "P30": 2,
    "P21": 0, "P25": 0, "P27": 4, "P23": 4, "P26": 5, "P19": 4,
    "P10": 2, "P18": 2, "P22": 1, "P2": 1, "P11": 2, "P17": 3, "P24": 2,
}

BLANK_MARKER = "__BLANK__"


def normalize_value(v):
    """値を正規化（blank と 0 を区別）"""
    if v is None or pd.isna(v):
        return BLANK_MARKER
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "none", "<na>", "blank"):
        return BLANK_MARKER
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s


def main():
    if not CSV_PATH.exists():
        print(f"❌ CSV が見つかりません: {CSV_PATH}")
        return 1
    if not GT_PATH.exists():
        print(f"❌ GT ファイルが見つかりません: {GT_PATH}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # CSV読み込み
    # ============================================================
    print("【CSV読み込み】")
    csv_df = None
    used_encoding = None
    for enc in ["utf-8", "cp932", "utf-16", "iso-8859-1", "sjis"]:
        try:
            csv_df = pd.read_csv(CSV_PATH, encoding=enc, dtype=str)
            used_encoding = enc
            print(f"✅ エンコーディング: {enc}")
            break
        except Exception:
            continue

    if csv_df is None:
        print("❌ CSVを読み込めません")
        return 1

    print(f"CSV列数: {len(csv_df.columns)}")
    print(f"CSV行数: {len(csv_df)}")
    print()

    # ============================================================
    # GT読み込み
    # ============================================================
    gt_df = pd.read_csv(GT_PATH, dtype=str)
    page_to_row = {}
    for idx, row in gt_df.iterrows():
        page = row["page"]
        page_to_row[page] = idx

    print(f"GT ページ数: {len(gt_df)}")
    print()

    # ============================================================
    # やること1: 全列棚卸し
    # ============================================================
    print("【全列棚卸し】")

    inventory_rows = []
    for col_idx, header in enumerate(csv_df.columns):
        col_data = csv_df[header].astype(str)
        non_empty = col_data[col_data.str.strip() != ""].count()
        empty = len(col_data) - non_empty
        unique = col_data.nunique()
        samples = col_data.dropna().unique()[:3]

        # 数値判定
        numeric_count = 0
        min_val, max_val = None, None
        for v in col_data:
            try:
                num = float(v)
                numeric_count += 1
                if min_val is None or num < min_val:
                    min_val = num
                if max_val is None or num > max_val:
                    max_val = num
            except (ValueError, TypeError):
                pass

        inventory_rows.append({
            "column_index_0_based": col_idx,
            "column_index_1_based": col_idx + 1,
            "header": header,
            "non_empty_count": non_empty,
            "empty_count": empty,
            "unique_count": unique,
            "sample_values": " | ".join(map(str, samples[:3])),
            "numeric_like_count": numeric_count,
            "min_value": min_val if min_val is not None else "",
            "max_value": max_val if max_val is not None else "",
            "notes": "",
        })

    inventory = pd.DataFrame(inventory_rows)
    inventory_csv = OUTPUT_DIR / "salesforce_csv_header_inventory.csv"
    inventory.to_csv(inventory_csv, index=False, encoding="utf-8-sig")
    print(f"✅ {inventory_csv}")
    print()

    # ============================================================
    # やること2: 候補列抽出（ヘッダー名から）
    # ============================================================
    print("【候補列抽出（ヘッダー名）】")

    keywords = [
        "ai", "ａｉ", "合計", "総数", "紹介", "新規", "ターゲット",
        "導入", "未利用", "引越", "商材",
    ]

    candidate_rows = []
    for idx, row in inventory.iterrows():
        header = row["header"].lower()
        reason = []

        for kw in keywords:
            if kw in header:
                reason.append(kw)

        # 値のレンジが 0-9 程度の列
        try:
            max_val = float(row["max_value"]) if row["max_value"] else None
            min_val = float(row["min_value"]) if row["min_value"] else None
            if max_val and 0 <= max_val <= 50:
                reason.append("value_range_0_50")
        except (ValueError, TypeError):
            pass

        if reason:
            candidate_rows.append({
                "column_index_0_based": row["column_index_0_based"],
                "column_index_1_based": row["column_index_1_based"],
                "header": row["header"],
                "candidate_reason": " | ".join(reason),
                "match_count_against_pdf_visual": 0,
                "evaluated_count": 0,
                "match_rate_against_pdf_visual": 0.0,
                "mismatch_pages": "",
                "sample_page_values": "",
                "notes": "",
            })

    candidates_by_header = pd.DataFrame(candidate_rows)
    candidates_csv = OUTPUT_DIR / "ai_total_candidate_columns.csv"
    candidates_by_header.to_csv(candidates_csv, index=False, encoding="utf-8-sig")
    print(f"✅ {candidates_csv} ({len(candidates_by_header)}行)")
    print()

    # ============================================================
    # やること3: 全列スコアリング
    # ============================================================
    print("【全列スコアリング】")

    target_pages = list(PDF_VISUAL_AI_TOTAL.keys())

    score_rows = []
    for col_idx, header in enumerate(csv_df.columns):
        col_data = csv_df[header].astype(str)

        # 対象ページについて評価
        matched = 0
        evaluated = 0
        mismatch_pages = []
        matched_pages = []

        for page in target_pages:
            if page not in page_to_row:
                continue

            gt_idx = page_to_row[page]
            csv_value_norm = normalize_value(col_data.iloc[gt_idx])
            pdf_value_norm = normalize_value(PDF_VISUAL_AI_TOTAL[page])

            evaluated += 1
            if csv_value_norm == pdf_value_norm:
                matched += 1
                matched_pages.append(page)
            else:
                mismatch_pages.append(f"{page}({csv_value_norm})")

        match_rate = (matched / evaluated * 100) if evaluated > 0 else 0.0

        # サンプル値取得
        samples = col_data.dropna().unique()[:3]

        score_rows.append({
            "column_index_0_based": col_idx,
            "column_index_1_based": col_idx + 1,
            "header": header,
            "evaluated_count": evaluated,
            "match_count": matched,
            "match_rate": round(match_rate, 2),
            "mismatch_count": evaluated - matched,
            "mismatch_pages": " | ".join(mismatch_pages) if mismatch_pages else "",
            "matched_pages": " | ".join(matched_pages) if matched_pages else "",
            "sample_values": " | ".join(map(str, samples[:3])),
            "rank": 0,
        })

    score_df = pd.DataFrame(score_rows)
    score_df = score_df.sort_values("match_rate", ascending=False).reset_index(drop=True)
    score_df["rank"] = range(1, len(score_df) + 1)

    score_csv = OUTPUT_DIR / "ai_total_column_match_score_all_columns.csv"
    score_df.to_csv(score_csv, index=False, encoding="utf-8-sig")
    print(f"✅ {score_csv}")
    print()

    # 上位10表示
    print("【スコアリング上位10】")
    for idx, row in score_df.head(10).iterrows():
        print(f"  {row['rank']}位: 列{row['column_index_1_based']:3} | {row['header']:30} | "
              f"{row['match_count']}/{row['evaluated_count']} ({row['match_rate']:.1f}%)")

    print()

    # ============================================================
    # やること4: 上位候補列の詳細比較
    # ============================================================
    print("【上位候補列の詳細比較】")

    top_candidates = score_df.head(10)
    col_35_row = score_df[score_df["column_index_1_based"] == 35].iloc[0] if len(score_df[score_df["column_index_1_based"] == 35]) > 0 else None

    detail_rows = []

    candidate_indices = list(top_candidates["column_index_0_based"]) + [34]  # 34 = col35 (0-indexed)
    candidate_indices = list(set(candidate_indices))

    for page in target_pages:
        if page not in page_to_row:
            continue

        gt_idx = page_to_row[page]
        pdf_value = PDF_VISUAL_AI_TOTAL[page]

        for cand_col_idx in candidate_indices:
            if cand_col_idx >= len(csv_df.columns):
                continue

            header = csv_df.columns[cand_col_idx]
            csv_value = csv_df.iloc[gt_idx, cand_col_idx]
            csv_value_norm = normalize_value(csv_value)
            pdf_value_norm = normalize_value(pdf_value)
            is_match = (csv_value_norm == pdf_value_norm)

            v3_value = gt_df.iloc[gt_idx]["v3_ai_total"]
            v22_value = gt_df.iloc[gt_idx]["v22_ai_total"]
            existing_col35 = gt_df.iloc[gt_idx]["csv_ai_total"]

            detail_rows.append({
                "page": page,
                "pdf_visual_ai_total": pdf_value,
                "candidate_column_index_1_based": cand_col_idx + 1,
                "candidate_header": header,
                "candidate_csv_value": csv_value_norm,
                "is_match": "YES" if is_match else "NO",
                "v3_value": v3_value,
                "v22_value": v22_value,
                "existing_csv_value_from_old_column35": existing_col35,
                "note": "",
            })

    detail_df = pd.DataFrame(detail_rows)
    detail_csv = OUTPUT_DIR / "ai_total_top_candidate_column_comparison.csv"
    detail_df.to_csv(detail_csv, index=False, encoding="utf-8-sig")
    print(f"✅ {detail_csv}")
    print()

    # ============================================================
    # 統計
    # ============================================================
    print("【統計】")
    print(f"CSV列35（紹介総数）の一致率: {col_35_row['match_rate'] if col_35_row is not None else 'N/A'}%")
    print(f"最高一致率の列: 列{top_candidates.iloc[0]['column_index_1_based']} "
          f"({top_candidates.iloc[0]['header']}) "
          f"{top_candidates.iloc[0]['match_rate']:.1f}%")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

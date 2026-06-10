# -*- coding: utf-8 -*-
"""
Phase 1: アンサンブル Tier スコアラー

目的:
    PDF目視正解（GT v2）を基準に、v3 / V2.2 / CSV の
    単独・一致 Tier 別カバレッジと一致率を再計算する。

入力:
    data/test_outputs/phase5_pdf_visual_accuracy_recount_detail_v2.csv

出力:
    data/test_outputs/ground_truth_audit_v2/ensemble_tier_score_summary.csv
    data/test_outputs/ground_truth_audit_v2/ensemble_tier_score_detail.csv

注意:
    - blank（空欄/NaN）と 0 は区別する
    - GT監査前のスコアは「暫定」。再目視確認後に再実行して正本化する
"""

import sys
from pathlib import Path

import pandas as pd

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

INPUT_CSV = Path("data/test_outputs/phase5_pdf_visual_accuracy_recount_detail_v2.csv")
OUTPUT_DIR = Path("data/test_outputs/ground_truth_audit_v2")
SUMMARY_CSV = OUTPUT_DIR / "ensemble_tier_score_summary.csv"
DETAIL_CSV = OUTPUT_DIR / "ensemble_tier_score_detail.csv"

BLANK = "__BLANK__"  # 空欄/NaN を 0 と区別するための内部表現


def norm(value):
    """値を正規化する。空欄/NaN は BLANK、数値は int 化した文字列にする。

    blank と 0 を混同しないことが最重要。
    """
    if value is None:
        return BLANK
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none", "<na>", "blank"):
        return BLANK
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s  # uncertain 等はそのまま


def main() -> int:
    if not INPUT_CSV.exists():
        print(f"❌ 入力ファイルが見つかりません: {INPUT_CSV}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INPUT_CSV, dtype=str)
    n_total = len(df)
    print(f"入力: {INPUT_CSV} ({n_total}ページ)")
    print()

    # 正規化列
    df["gt"] = df["pdf_visual_ai_total"].map(norm)
    df["v3"] = df["v3_ai_total"].map(norm)
    df["v22"] = df["v22_ai_total"].map(norm)
    df["csv"] = df["csv_ai_total"].map(norm)

    # 単独一致フラグ
    df["v3_match"] = df["v3"] == df["gt"]
    df["v22_match"] = df["v22"] == df["gt"]
    df["csv_match"] = df["csv"] == df["gt"]

    # 一致 Tier フラグ
    df["tier_v3_eq_v22"] = df["v3"] == df["v22"]
    df["tier_v3_eq_v22_eq_csv"] = (df["v3"] == df["v22"]) & (df["v22"] == df["csv"])
    df["tier_v3_eq_csv"] = df["v3"] == df["csv"]
    df["tier_v22_eq_csv"] = df["v22"] == df["csv"]
    df["tier_all_disagree"] = (
        (df["v3"] != df["v22"]) & (df["v22"] != df["csv"]) & (df["v3"] != df["csv"])
    )

    # ============ サマリー集計 ============
    rows = []

    def add(metric, mask, match_col, note=""):
        sub = df[mask]
        count = len(sub)
        matched = int(sub[match_col].sum()) if count > 0 else 0
        rate = round(matched / count * 100, 2) if count > 0 else None
        rows.append({
            "metric": metric,
            "coverage": count,
            "coverage_pct": round(count / n_total * 100, 2),
            "match_count": matched,
            "match_rate_pct": rate,
            "note": note,
        })

    all_mask = pd.Series([True] * n_total, index=df.index)
    add("v3_single", all_mask, "v3_match", "v3単独の全ページ一致率")
    add("v22_single", all_mask, "v22_match", "V2.2単独の全ページ一致率")
    add("csv_single", all_mask, "csv_match", "CSV単独の全ページ一致率")

    add("tier_v3_eq_v22", df["tier_v3_eq_v22"], "v3_match",
        "v3==v22 のページ（v3値でGT照合）")
    add("tier_v3_eq_v22_eq_csv", df["tier_v3_eq_v22_eq_csv"], "v3_match",
        "3ソース完全一致ページ")
    add("tier_v3_eq_csv", df["tier_v3_eq_csv"], "v3_match",
        "v3==csv のページ")
    add("tier_v22_eq_csv", df["tier_v22_eq_csv"], "v22_match",
        "v22==csv のページ")

    # all_disagree: どのソースがGTに一致したか
    dis = df[df["tier_all_disagree"]]
    dis_count = len(dis)
    rows.append({
        "metric": "tier_all_disagree",
        "coverage": dis_count,
        "coverage_pct": round(dis_count / n_total * 100, 2),
        "match_count": "",
        "match_rate_pct": "",
        "note": (
            f"3ソースが割れたページ: v3一致={int(dis['v3_match'].sum())}件 / "
            f"v22一致={int(dis['v22_match'].sum())}件 / "
            f"csv一致={int(dis['csv_match'].sum())}件"
        ) if dis_count > 0 else "該当なし",
    })

    summary = pd.DataFrame(rows)
    summary.to_csv(SUMMARY_CSV, index=False, encoding="utf-8-sig")

    # ============ 詳細出力 ============
    detail_cols = [
        "page", "gt", "v3", "v22", "csv",
        "v3_match", "v22_match", "csv_match",
        "tier_v3_eq_v22", "tier_v3_eq_v22_eq_csv",
        "tier_v3_eq_csv", "tier_v22_eq_csv", "tier_all_disagree",
        "gt_source", "gt_audit_status",
    ]
    detail = df[[c for c in detail_cols if c in df.columns]].copy()
    detail.to_csv(DETAIL_CSV, index=False, encoding="utf-8-sig")

    # ============ 表示 ============
    print("=" * 90)
    print("【Tier 別スコア（GT監査前・暫定）】")
    print("=" * 90)
    print(summary.to_string(index=False))
    print()
    print(f"✅ サマリー: {SUMMARY_CSV}")
    print(f"✅ 詳細:     {DETAIL_CSV}")
    print()
    print("⚠️ 本スコアは GT 監査前の暫定値です。再目視確認後に再実行してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

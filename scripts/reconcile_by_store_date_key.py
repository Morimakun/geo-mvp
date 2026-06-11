# -*- coding: utf-8 -*-
"""
Phase 3: 店舗×日付キーによる正式再照合

PDF帳票30ページをSalesforce CSVと正式に照合。
- ページ順比較ではなく、店舗（取扱コード）× 日付キーを使用
- AI合計欄（CSV列35）と CZ合計欄（CSV列104）を検証
- 再送FAX・イベント/店頭・CSV対象期間外を別ステータスで管理
"""

import sys, io
from pathlib import Path
import pandas as pd

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUTPUT_DIR = Path("data/test_outputs/store_date_reconciliation")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================================
# 店舗マスター（Excelより抽出済み）
# ==========================================================
STORE_MASTER = {
    "小倉": "AU1K0024112", "深江橋": "AU1K0024104",
    "守口南寺方": "AU1KW740082", "ニトリモール枚方": "AU1KW740165",
    "くずはモール": "AU1KC901225", "魚住": "AU1KC490278",
    "イオンモール大日": "AU1KC490237", "広畑": "AU1KC400079",
    "宝殿": "AU1KC400038", "JR神戸北": "AU1KC400020",
    "明石大久保": "AU1KC400012", "熊取": "AU1KC310039",
    "高石": "AU1KC310021", "鶴見緑地": "AU1KB830227",
    "堺北花田": "AU1KB830201", "布施": "AU1K4330093",
    "高砂明姫": "AU1K4280454", "羽曳野伊賀": "AU1K4150749",
    "イオンモール神戸北": "AU1K4050139", "ララポートEXPOCITY": "AU1K4050055",
    "JR六甲道": "AU1K3430050", "神戸ハーバーランド": "AU1K209A044",
    "松井山手": "AU1K0620604", "尼崎下坂部": "AU1K0620331",
}

# ==========================================================
# PDFページ別情報（FAXヘッダー・手書き日付から解読）
# ==========================================================
PDF_PAGES = {
    "P1":  ("小倉", "2026/05/17", "5/17"),
    "P2":  ("イオンモール大日", "2026/05/17", "5/17", "再送前"),
    "P3":  ("高石", "2026/05/17", "5/17"),
    "P4":  ("ニトリモール枚方", "2026/05/17", "5/17", "多頁1/4"),
    "P5":  (None, "2026/05/17", None, "店名なし"),
    "P6":  (None, "2026/05/17", None, "店名なし"),
    "P7":  ("堺北花田", "2026/05/17", "5/17"),
    "P8":  ("JR神戸北", "2026/05/17", "5/17"),
    "P9":  ("イオンモール神戸北", "2026/05/17", "5/17", "イベント(NO.1956 P.2)"),
    "P10": ("イオンモール大日", "2026/05/17", "5/17", "再送版"),
    "P11": ("深江橋", "2026/05/18", "5/18"),
    "P12": ("広畑", "2026/05/18", "5/18"),
    "P13": ("ニトリモール枚方", "2026/05/18", "5/18"),
    "P14": ("イオンモール神戸北", "2026/05/17", "5/17", "店頭(NO.1956 P.1)"),
    "P15": ("イオンモール大日", "2026/05/18", "5/18"),
    "P16": ("熊取", "2026/05/18", "5/18"),
    "P17": ("イオンモール神戸北", "2026/05/18", "5/18"),
    "P18": ("くずはモール", "2026/05/18", "5/18"),
    "P19": ("小倉", "2026/05/18", "5/18"),
    "P20": (None, "2026/05/18", None, "店名なし"),
    "P21": ("明石大久保", "2026/05/18", "5/18"),
    "P22": ("ララポートEXPOCITY", "2026/05/18", "5/18"),
    "P23": ("羽曳野伊賀", "2026/05/18", "5/18"),
    "P24": (None, "2026/05/18", None, "店名未特定"),
    "P25": ("高砂明姫", "2026/05/18", "5/18"),
    "P26": ("尼崎下坂部", "2026/05/19", "5/19", "5/19対象外"),
    "P27": ("羽曳野伊賀", "2026/05/19", "5/19", "5/19対象外"),
    "P28": ("宝殿", "2026/05/19", "5/19", "5/19対象外"),
    "P29": ("松井山手", "2026/05/18", "5/18"),
    "P30": ("JR神戸北", "2026/05/18", "5/18"),
}

# ==========================================================
# 将大さんPDF目視確認値（正本）
# ==========================================================
PDF_VISUAL = {
    "P1": {"AI": 5, "CZ": None}, "P2": {"AI": 1, "CZ": None},
    "P10": {"AI": 2, "CZ": None}, "P11": {"AI": 2, "CZ": None},
    "P14": {"AI": 3, "CZ": None}, "P16": {"AI": 9, "CZ": None},
    "P17": {"AI": 3, "CZ": None}, "P18": {"AI": 2, "CZ": None},
    "P19": {"AI": 4, "CZ": "blank"}, "P21": {"AI": 0, "CZ": None},
    "P22": {"AI": 1, "CZ": None}, "P23": {"AI": 4, "CZ": None},
    "P24": {"AI": 2, "CZ": None}, "P25": {"AI": 0, "CZ": None},
    "P26": {"AI": 5, "CZ": None}, "P27": {"AI": 4, "CZ": None},
    "P29": {"AI": None, "CZ": "blank"}, "P30": {"AI": 2, "CZ": None},
}

# ==========================================================
# CSV読み込み・索引化
# ==========================================================
csv = pd.read_csv("~/Downloads/report1780043296399.csv".replace("~", str(Path.home())),
                   encoding="cp932", dtype=str)
csv_index = {}
for idx, row in csv.iterrows():
    code = row.iloc[280]  # 列281（0-based=280）
    date = row.iloc[282]  # 列283（0-based=282）
    key = (code, date)
    if key not in csv_index:
        csv_index[key] = []
    csv_index[key].append(idx)

print(f"【CSV索引化】{len(csv_index)}個の店舗×日付キー")

# ==========================================================
# 照合実行
# ==========================================================
detail_rows = []
for page, page_info in sorted(PDF_PAGES.items()):
    store_name = page_info[0]
    pdf_date = page_info[1]  # YYYY/MM/DD
    pdf_visual = PDF_VISUAL.get(page, {})
    ai_visual = pdf_visual.get("AI")
    cz_visual = pdf_visual.get("CZ")

    # ステータス判定
    store_code = STORE_MASTER.get(store_name) if store_name else None
    is_unknown_store = store_name is None
    is_unknown_date = pdf_date is None
    is_out_of_period = pdf_date and pdf_date >= "2026/05/19"  # 5/19以降はCSV対象外
    is_resend = len(page_info) > 3 and ("再送" in page_info[3])
    is_event_storefront = len(page_info) > 3 and ("イベント" in page_info[3] or "店頭" in page_info[3])

    # CSV行検索
    csv_rows = []
    match_key_status = "unknown"
    if store_code and pdf_date:
        csv_rows = csv_index.get((store_code, pdf_date), [])
        if csv_rows:
            match_key_status = "matched" if len(csv_rows) == 1 else "multiple_csv_rows"
        elif is_out_of_period:
            match_key_status = "out_of_csv_period"
        elif is_unknown_store:
            match_key_status = "store_unknown"
        elif is_unknown_date:
            match_key_status = "date_unknown"
        else:
            match_key_status = "no_csv_row"

    # AI/CZ照合
    ai_match = None
    cz_match = None
    if csv_rows and ai_visual is not None:
        csv_ai_vals = [int(float(csv.iloc[r, 34])) for r in csv_rows]  # 列35（0-based=34）
        ai_match = ai_visual in csv_ai_vals
    if csv_rows and cz_visual is not None and cz_visual != "blank":
        csv_cz_vals = [csv.iloc[r, 103] for r in csv_rows]  # 列104（0-based=103）
        cz_match = cz_visual in csv_cz_vals

    # ステータス決定
    reconciliation_status = "unknown"
    if is_out_of_period:
        reconciliation_status = "excluded_out_of_period"
    elif is_resend:
        reconciliation_status = "excluded_resend_old_version"
    elif is_event_storefront:
        reconciliation_status = "event_storefront_needs_rule"
    elif is_unknown_store or is_unknown_date:
        reconciliation_status = "needs_manual_review"
    elif match_key_status == "no_csv_row":
        reconciliation_status = "needs_manual_review"
    elif match_key_status == "multiple_csv_rows":
        reconciliation_status = "needs_business_rule"
    elif ai_match and cz_visual in [None, "blank"]:
        reconciliation_status = "matched_ai_only"
    elif ai_match:
        reconciliation_status = "matched_ai_and_cz"
    elif ai_visual is not None and not ai_match:
        reconciliation_status = "mismatch"
    else:
        reconciliation_status = "matched_ai_and_cz" if (ai_match and cz_match) else "needs_manual_review"

    # 出力行
    csv_row = csv_rows[0] if len(csv_rows) == 1 else None
    row = {
        "page": page,
        "pdf_store_name_raw": store_name or "",
        "store_code": store_code or "",
        "pdf_report_date": pdf_date or "",
        "csv_row_index": csv_row + 1 if csv_row is not None else "",
        "match_key_status": match_key_status,
        "pdf_visual_ai_total": ai_visual if ai_visual is not None else "",
        "csv_ai_total_col35": int(float(csv.iloc[csv_row, 34])) if csv_row is not None else "",
        "ai_match": "✅ YES" if ai_match else ("❌ NO" if ai_match is False else "—"),
        "pdf_visual_cz_total": cz_visual or "",
        "csv_cz_total_col104": csv.iloc[csv_row, 103] if csv_row is not None else "",
        "cz_match": "✅ YES" if cz_match else ("❌ NO" if cz_match is False else "—"),
        "reconciliation_status": reconciliation_status,
        "special_case_type": "resend" if is_resend else ("event_storefront" if is_event_storefront else ("out_of_csv_period" if is_out_of_period else "none")),
        "note": page_info[3] if len(page_info) > 3 else "",
    }
    detail_rows.append(row)

detail_df = pd.DataFrame(detail_rows)
detail_path = OUTPUT_DIR / "store_date_key_reconciliation_detail.csv"
detail_df.to_csv(detail_path, index=False, encoding="utf-8-sig")
print(f"✅ {detail_path}")

# ==========================================================
# サマリー計算
# ==========================================================
summary_rows = [
    ("total_pdf_pages", len(detail_df), 30, "", "全PDFページ数"),
    ("key_matched_pages", len(detail_df[detail_df["match_key_status"] == "matched"]), 30, "", "店舗×日付キーで対応行が見つかったページ"),
    ("out_of_csv_period_pages", len(detail_df[detail_df["reconciliation_status"] == "excluded_out_of_period"]), 30, "", "CSV対象期間外（5/19以降）"),
    ("resend_candidate_pages", len(detail_df[detail_df["special_case_type"] == "resend"]), 30, "", "再送FAX候補"),
    ("event_storefront_rule_needed_pages", len(detail_df[detail_df["special_case_type"] == "event_storefront"]), 30, "", "イベント/店頭別分離が必要"),
    ("ai_evaluated_pages", len(detail_df[(detail_df["pdf_visual_ai_total"] != "") & (detail_df["match_key_status"] == "matched")]), None, "", "CSV対応行ありかつAI値評価可能"),
    ("ai_matched_pages", len(detail_df[(detail_df["ai_match"] == "✅ YES") & (detail_df["match_key_status"] == "matched")]), None, "", "AI値が一致"),
    ("ai_mismatch_pages", len(detail_df[(detail_df["ai_match"] == "❌ NO") & (detail_df["match_key_status"] == "matched")]), None, "", "AI値が不一致"),
]

summary_df = pd.DataFrame([
    {"metric": m, "count": c, "denominator": d, "note": n}
    for m, c, d, _, n in summary_rows
])

# 一致率計算
ai_eval = len(detail_df[(detail_df["pdf_visual_ai_total"] != "") & (detail_df["match_key_status"] == "matched")])
ai_match = len(detail_df[(detail_df["ai_match"] == "✅ YES") & (detail_df["match_key_status"] == "matched")])
if ai_eval > 0:
    summary_df = pd.concat([summary_df, pd.DataFrame({
        "metric": ["ai_match_rate"],
        "count": [ai_match],
        "denominator": [ai_eval],
        "note": [f"{ai_match}/{ai_eval}"]
    })], ignore_index=True)

summary_path = OUTPUT_DIR / "store_date_key_reconciliation_summary.csv"
summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
print(f"✅ {summary_path}")

print()
print(f"【照合結果サマリー】")
for _, row in summary_df.iterrows():
    print(f"  {row['metric']:40} : {row['count']:>3} / {row['denominator'] if row['denominator'] else '—':>3}  ({row['note']})")


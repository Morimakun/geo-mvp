"""
Phase 6B: Confirmation-Support Tool Metrics (Evaluation Axis Reframe)

目的:
  match_rate中心の評価から、確認支援ツールとしての主指標へ転換する。
  - 自動確定率 / 要確認率 / 誤確定率(false-confirm) / 要確認捕捉率 / 見逃し(false-negative) / 作業削減見込み
  - false-confirm（不一致なのに一致と確定）を最重要リスク=目標0として扱う

入力（既存CSVのみ・Vision API再実行なし）:
  - phase6b_v3_reconciliation_field_comparisons.csv
  - phase6b_hybrid_az_hi40_30pages_field_comparisons.csv

Tier設計（ユーザー確定版）:
  Tier A : AI(合計), store_code   印字数字 → 自動確定可
  Tier B : existing_support(HH-IO) / new_options(GS-HG)
           条件付き自動確定。new_optionsは「正の字欄寄り」として
           uncertain / 0疑義 / 正の字途中形 / 空欄疑義 は review に落とす
  Tier C : AU/AV/AY/AZ(正の字)     自動確定しない。matchしても「参考一致」扱い

出力:
  - phase6b_confirmation_metrics_summary.csv
  - phase6b_confirmation_metrics_by_tier.csv
  - phase6b_false_confirm_audit.csv
"""

import sys
from pathlib import Path
import pandas as pd

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "test_outputs"
V3_CSV = OUTPUT_DIR / "phase6b_v3_reconciliation_field_comparisons.csv"
HYBRID_CSV = OUTPUT_DIR / "phase6b_hybrid_az_hi40_30pages_field_comparisons.csv"

print("=" * 100)
print("Phase 6B: Confirmation-Support Tool Metrics (Evaluation Axis Reframe)")
print("=" * 100)
print()

# ---------------------------------------------------------------------------
# Tier mapping
# ---------------------------------------------------------------------------
def col_to_num(code):
    """Excel-style column code -> number (A=1, AA=27...)."""
    if not isinstance(code, str) or code == '' or str(code).lower() == 'nan':
        return -1
    code = code.strip().upper()
    num = 0
    for ch in code:
        if not ('A' <= ch <= 'Z'):
            return -1
        num = num * 26 + (ord(ch) - ord('A') + 1)
    return num

def get_tier(code):
    """Map csv_column_code -> tier label."""
    if code == 'AI':
        return 'A_printed'          # 合計（印字数字）
    if code in ('AU', 'AV', 'AY', 'AZ'):
        return 'C_tally'            # 正の字（手書き）
    n = col_to_num(code)
    if 201 <= n <= 215:             # GS..HG
        return 'B_newopt'           # 新規オプション（正の字欄寄り）
    if 216 <= n <= 249:             # HH..IO
        return 'B_existing'         # 既存対応
    return 'other'

TIER_LABEL = {
    'A_printed': 'Tier A (印字数字: AI)',
    'B_existing': 'Tier B (既存対応 HH-IO)',
    'B_newopt': 'Tier B (新規オプション GS-HG, 正の字寄り)',
    'C_tally': 'Tier C (正の字 AU/AV/AY/AZ)',
    'other': 'Other (内訳/その他欄)',
}

# ---------------------------------------------------------------------------
# Decision logic (status + tier -> tool decision)
# ---------------------------------------------------------------------------
def is_zeroish(v):
    return str(v).strip() in ('0', '0.0')

def is_uncertain(v):
    return str(v).strip().lower() == 'uncertain'

def decide(status, tier, pdf_value, reason):
    """Map a reconciliation row into the tool's confirmation decision."""
    reason = '' if pd.isna(reason) else str(reason)

    if status == 'match':
        if tier == 'A_printed':
            return 'AUTO_CONFIRM'
        if tier == 'B_existing':
            return 'AUTO_CONFIRM'
        if tier == 'B_newopt':
            # 正の字欄寄り: 0疑義 / 途中形 / uncertain は review に落とす
            if is_zeroish(pdf_value) or is_uncertain(pdf_value) or '途中形' in reason:
                return 'FLAG'
            return 'AUTO_CONFIRM'
        if tier == 'C_tally':
            return 'REFERENCE_MATCH'   # 自動確定しない（参考一致）
        return 'AUTO_CONFIRM'          # other 印字欄はデフォルト確定
    if status == 'mismatch':
        return 'FLAG'
    if status == 'skipped_pdf_uncertain':
        return 'FLAG'
    if status == 'skipped_csv_null':
        return 'FLAG'                  # PDFに値あり/CSV空欄 = 潜在的不一致
    if status in ('skipped_pdf_null', 'skipped_both_null'):
        return 'SKIP'
    return 'SKIP'

# ---------------------------------------------------------------------------
# Load and classify a reconciliation dataframe
# ---------------------------------------------------------------------------
def load_and_classify(csv_path, status_col):
    df = pd.read_csv(csv_path, dtype=str)
    df.columns = [c.lstrip('﻿') for c in df.columns]
    df['tier'] = df['csv_column_code'].apply(get_tier)
    df['decision'] = df.apply(
        lambda r: decide(r[status_col], r['tier'], r.get('pdf_value'), r.get('reason')),
        axis=1
    )
    return df

print("Loading v3 and hybrid reconciliation data...")
df_v3 = load_and_classify(V3_CSV, 'comparison_status')
df_hy = load_and_classify(HYBRID_CSV, 'comparison_status_new')
print(f"  v3: {len(df_v3)} rows, hybrid: {len(df_hy)} rows")
print()

# ---------------------------------------------------------------------------
# Compute headline KPIs
# ---------------------------------------------------------------------------
def compute_kpis(df, label):
    auto = (df['decision'] == 'AUTO_CONFIRM').sum()
    flag = (df['decision'] == 'FLAG').sum()
    ref = (df['decision'] == 'REFERENCE_MATCH').sum()
    skip = (df['decision'] == 'SKIP').sum()
    active = auto + flag + ref          # 確認対象（人間が見うる対象）

    auto_rate = auto / active * 100 if active else 0
    review_rate = flag / active * 100 if active else 0
    ref_rate = ref / active * 100 if active else 0
    # 作業削減見込み: 自動確定で人間の確認から外せた割合
    work_reduction = auto / active * 100 if active else 0

    print(f"[{label}]")
    print(f"  AUTO_CONFIRM (自動確定):   {auto}")
    print(f"  FLAG (要確認):             {flag}")
    print(f"  REFERENCE_MATCH (参考一致): {ref}  ← Tier C, 自動確定しない")
    print(f"  SKIP (対象外/値なし):       {skip}")
    print(f"  --- active(確認対象)=AUTO+FLAG+REF = {active}")
    print(f"  自動確定率: {auto_rate:.1f}%")
    print(f"  要確認率:   {review_rate:.1f}%")
    print(f"  参考一致率: {ref_rate:.1f}%")
    print(f"  作業削減見込み: {work_reduction:.1f}%")
    print()
    return {
        'version': label, 'auto_confirm': auto, 'flag': flag,
        'reference_match': ref, 'skip': skip, 'active': active,
        'auto_confirm_rate': round(auto_rate, 1),
        'review_rate': round(review_rate, 1),
        'reference_rate': round(ref_rate, 1),
        'work_reduction_est': round(work_reduction, 1),
    }

print("-" * 100)
print("Headline KPIs")
print("-" * 100)
print()
kpi_v3 = compute_kpis(df_v3, 'v3')
kpi_hy = compute_kpis(df_hy, 'hybrid')

# ---------------------------------------------------------------------------
# Per-tier breakdown
# ---------------------------------------------------------------------------
def tier_breakdown(df, version):
    rows = []
    for tier in ['A_printed', 'B_existing', 'B_newopt', 'C_tally', 'other']:
        sub = df[df['tier'] == tier]
        auto = (sub['decision'] == 'AUTO_CONFIRM').sum()
        flag = (sub['decision'] == 'FLAG').sum()
        ref = (sub['decision'] == 'REFERENCE_MATCH').sum()
        skip = (sub['decision'] == 'SKIP').sum()
        active = auto + flag + ref
        rows.append({
            'version': version, 'tier': tier, 'tier_label': TIER_LABEL[tier],
            'auto_confirm': auto, 'flag': flag, 'reference_match': ref,
            'skip': skip, 'active': active,
            'auto_confirm_rate': round(auto / active * 100, 1) if active else 0.0,
            'policy': {
                'A_printed': '自動確定可',
                'B_existing': '条件付き自動確定',
                'B_newopt': '条件付き自動確定(0/途中形/uncertainはreview)',
                'C_tally': '自動確定しない(参考一致のみ)',
                'other': 'デフォルト確定(印字欄)',
            }[tier],
        })
    return rows

print("-" * 100)
print("Per-Tier Breakdown")
print("-" * 100)
print()
tier_rows = tier_breakdown(df_v3, 'v3') + tier_breakdown(df_hy, 'hybrid')
df_tier = pd.DataFrame(tier_rows)
for _, r in df_tier.iterrows():
    print(f"  [{r['version']:<6}] {r['tier_label']:<42} "
          f"AUTO={r['auto_confirm']:<3} FLAG={r['flag']:<3} REF={r['reference_match']:<3} "
          f"SKIP={r['skip']:<5} auto率={r['auto_confirm_rate']}%")
print()

# ---------------------------------------------------------------------------
# False-confirm audit on human-verified subset
# ---------------------------------------------------------------------------
# 目視検証済み ground truth: (page_index, field_code) -> actual FAX value
VERIFIED = {
    (0, 'AZ'):  {'actual': '5',       'note': '正の字5本（目視）'},
    (5, 'AZ'):  {'actual': '30',      'note': '集計値30=3本+0（目視）'},
    (7, 'AZ'):  {'actual': '',        'note': '空欄（目視）'},
    (9, 'AZ'):  {'actual': 'unclear', 'note': '不鮮明・正の字1-2推定（目視）'},
    (14, 'AZ'): {'actual': '1',       'note': 'タリー約1本（目視）'},
    (28, 'HI'): {'actual': '',        'note': 'テンプレ印字40の誤読、実際は空欄（目視）'},
}

def meaningful(v):
    s = str(v).strip().lower()
    return s not in ('', 'nan', 'none', 'null', 'unclear', 'uncertain')

def audit_row(df, status_col, page_index, field_code, actual, note, version):
    sub = df[(df['page_number'].astype(str) == str(page_index)) &
             (df['csv_column_code'] == field_code)]
    if len(sub) == 0:
        return None
    row = sub.iloc[0]
    pdf_used = row.get('pdf_value')
    csv_val = row.get('csv_value')
    decision = row['decision']

    actual_meaningful = meaningful(actual)
    csv_meaningful = meaningful(csv_val)

    # 実際のFAX vs Salesforce(CSV) の真の不一致判定
    if actual_meaningful and csv_meaningful:
        real_discrepancy = str(actual).strip() != str(csv_val).strip().rstrip('.0').rstrip('.') \
                           and float_ne(actual, csv_val)
    elif actual_meaningful and not csv_meaningful:
        real_discrepancy = True    # FAXに値あり/SF空欄
    else:
        real_discrepancy = False   # FAX空欄

    # 監査カテゴリ
    if decision == 'AUTO_CONFIRM':
        # ツールが「一致」と確定。実FAX != csv なら誤確定
        if actual_meaningful and csv_meaningful and float_ne(actual, csv_val):
            category = 'FALSE_CONFIRM'   # 最重要リスク
        elif not actual_meaningful and csv_meaningful:
            category = 'FALSE_CONFIRM'   # 空欄を値と確定
        else:
            category = 'TRUE_CONFIRM'
    elif decision in ('FLAG',):
        if real_discrepancy:
            category = 'TRUE_FLAG'       # 実差を正しく捕捉
        else:
            category = 'FALSE_FLAG'      # ノイズ（抽出誤りで騒いだ）
    elif decision == 'REFERENCE_MATCH':
        category = 'REFERENCE_ONLY'
    else:  # SKIP
        if actual_meaningful and csv_meaningful and float_ne(actual, csv_val):
            category = 'MISSED'          # 見逃し（実差をSKIP）
        elif actual_meaningful and not csv_meaningful:
            category = 'RECALL_GAP'      # 抽出見逃し（SF空欄で実害なし）
        else:
            category = 'CORRECT_SKIP'

    return {
        'version': version, 'page_index': page_index, 'field_code': field_code,
        'actual_fax': actual, 'pdf_extracted': pdf_used, 'csv_value': csv_val,
        'decision': decision, 'audit_category': category,
        'real_discrepancy': real_discrepancy, 'note': note,
    }

def float_ne(a, b):
    """True if a != b numerically (fallback to string)."""
    try:
        return float(a) != float(b)
    except (ValueError, TypeError):
        return str(a).strip() != str(b).strip()

print("-" * 100)
print("False-Confirm Audit (目視検証済みサブセット)")
print("-" * 100)
print()

audit_records = []
for (pi, fc), info in VERIFIED.items():
    for df, scol, ver in [(df_v3, 'comparison_status', 'v3'),
                          (df_hy, 'comparison_status_new', 'hybrid')]:
        rec = audit_row(df, scol, pi, fc, info['actual'], info['note'], ver)
        if rec:
            audit_records.append(rec)

df_audit = pd.DataFrame(audit_records)
for _, r in df_audit.iterrows():
    print(f"  [{r['version']:<6}] P{r['page_index']+1:02d} {r['field_code']}: "
          f"FAX実={str(r['actual_fax']):<8} 抽出={str(r['pdf_extracted']):<6} "
          f"CSV={str(r['csv_value']):<6} 判断={r['decision']:<15} → {r['audit_category']}")
print()

# Audit aggregates
def audit_counts(df, version):
    sub = df[df['version'] == version]
    return {
        'false_confirm': (sub['audit_category'] == 'FALSE_CONFIRM').sum(),
        'true_flag': (sub['audit_category'] == 'TRUE_FLAG').sum(),
        'false_flag': (sub['audit_category'] == 'FALSE_FLAG').sum(),
        'missed': (sub['audit_category'] == 'MISSED').sum(),
        'recall_gap': (sub['audit_category'] == 'RECALL_GAP').sum(),
        'correct_skip': (sub['audit_category'] == 'CORRECT_SKIP').sum(),
        'reference_only': (sub['audit_category'] == 'REFERENCE_ONLY').sum(),
    }

ac_v3 = audit_counts(df_audit, 'v3')
ac_hy = audit_counts(df_audit, 'hybrid')

# 要確認捕捉率 = true_flag / (true_flag + missed)  [実差を何割拾えたか]
def capture_rate(ac):
    denom = ac['true_flag'] + ac['missed']
    return round(ac['true_flag'] / denom * 100, 1) if denom else None

print(f"  検証サブセット監査:")
print(f"    {'指標':<22} {'v3':>8} {'hybrid':>8}")
print(f"    {'誤確定(false-confirm)':<22} {ac_v3['false_confirm']:>8} {ac_hy['false_confirm']:>8}  ← 目標0")
print(f"    {'真陽性FLAG(true-flag)':<22} {ac_v3['true_flag']:>8} {ac_hy['true_flag']:>8}")
print(f"    {'偽陽性FLAG(false-flag)':<22} {ac_v3['false_flag']:>8} {ac_hy['false_flag']:>8}")
print(f"    {'見逃し(missed)':<22} {ac_v3['missed']:>8} {ac_hy['missed']:>8}")
print(f"    {'抽出見逃し(recall-gap)':<22} {ac_v3['recall_gap']:>8} {ac_hy['recall_gap']:>8}")
print(f"    {'正しい空欄(correct-skip)':<22} {ac_v3['correct_skip']:>8} {ac_hy['correct_skip']:>8}")
print(f"    要確認捕捉率: v3={capture_rate(ac_v3)}%  hybrid={capture_rate(ac_hy)}%")
print()

# ---------------------------------------------------------------------------
# Save outputs
# ---------------------------------------------------------------------------
print("-" * 100)
print("Saving outputs")
print("-" * 100)

# Summary
summary_rows = []
for kpi, ac, ver in [(kpi_v3, ac_v3, 'v3'), (kpi_hy, ac_hy, 'hybrid')]:
    summary_rows.append({
        'version': ver,
        'auto_confirm': kpi['auto_confirm'],
        'flag': kpi['flag'],
        'reference_match': kpi['reference_match'],
        'skip': kpi['skip'],
        'active_compared': kpi['active'],
        'auto_confirm_rate_%': kpi['auto_confirm_rate'],
        'review_rate_%': kpi['review_rate'],
        'reference_rate_%': kpi['reference_rate'],
        'work_reduction_est_%': kpi['work_reduction_est'],
        'false_confirm_verified': ac['false_confirm'],
        'true_flag_verified': ac['true_flag'],
        'false_flag_verified': ac['false_flag'],
        'missed_verified': ac['missed'],
        'recall_gap_verified': ac['recall_gap'],
        'review_capture_rate_%': capture_rate(ac),
    })
pd.DataFrame(summary_rows).to_csv(
    OUTPUT_DIR / "phase6b_confirmation_metrics_summary.csv",
    index=False, encoding='utf-8-sig'
)
print("  Summary: phase6b_confirmation_metrics_summary.csv")

df_tier.to_csv(
    OUTPUT_DIR / "phase6b_confirmation_metrics_by_tier.csv",
    index=False, encoding='utf-8-sig'
)
print("  By tier: phase6b_confirmation_metrics_by_tier.csv")

df_audit.to_csv(
    OUTPUT_DIR / "phase6b_false_confirm_audit.csv",
    index=False, encoding='utf-8-sig'
)
print("  Audit: phase6b_false_confirm_audit.csv")
print()

print("=" * 100)
print("Confirmation metrics evaluation complete.")
print("=" * 100)

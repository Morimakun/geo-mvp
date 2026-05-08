"""
FAX帳票 × Salesforce CSV 照合ロジック

照合エンジン（CSV読込 → マッチング → ステータス判定 → 結果出力）
このモジュールは test_reconciliation.py と app.py の両方から import される
"""

import csv
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


# ===== データ構造 =====

@dataclass
class ExtractionResult:
    """Vision API抽出結果"""
    file_name: str
    date: Optional[str]
    store_name: Optional[str]
    staff_name: Optional[str]
    daily_report_no: Optional[str]
    tablet_no: Optional[str]
    left_totals: List[str]  # ["29", "9", "3"] or []
    right_totals: List[str]  # ["27", "5"] or []
    needs_review: bool


@dataclass
class SalesforceRecord:
    """Salesforce CSV レコード"""
    date: str
    store_name: str
    staff_name: str
    daily_report_no: str
    tablet_no: str
    left_total_1: str
    left_total_2: str
    left_total_3: str
    right_total_1: str
    right_total_2: str

    def get_left_totals(self) -> List[str]:
        return [self.left_total_1, self.left_total_2, self.left_total_3]

    def get_right_totals(self) -> List[str]:
        return [self.right_total_1, self.right_total_2]


@dataclass
class ReconciliationResult:
    """照合結果"""
    file_name: str
    matching_key: str  # "DataNo" | "TabNo" | "複合キー"
    extraction: ExtractionResult
    matched_record: Optional[SalesforceRecord]
    status: str  # "一致" | "不一致" | "要確認"
    differences: List[str]
    review_reasons: List[str]


# ===== CSV読込 =====

def load_extraction_results(csv_path: str) -> List[ExtractionResult]:
    """Vision API抽出結果を読込"""
    results = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # left_totals と right_totals を parse
            left_totals = [v.strip() for v in row['left_totals'].split('/') if v.strip()] if row['left_totals'] else []
            right_totals = [v.strip() for v in row['right_totals'].split('/') if v.strip()] if row['right_totals'] else []

            result = ExtractionResult(
                file_name=row['file_name'],
                date=row['date'] if row['date'] else None,
                store_name=row['store_name'] if row['store_name'] else None,
                staff_name=row['staff_name'] if row['staff_name'] else None,
                daily_report_no=row['daily_report_no'] if row['daily_report_no'] else None,
                tablet_no=row['tablet_no'] if row['tablet_no'] else None,
                left_totals=left_totals,
                right_totals=right_totals,
                needs_review=row['needs_review'].lower() == 'true'
            )
            results.append(result)
    return results


def load_salesforce_csv(csv_path: str) -> List[SalesforceRecord]:
    """Salesforce CSV を読込"""
    records = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = SalesforceRecord(
                date=row['date'],
                store_name=row['store_name'],
                staff_name=row['staff_name'],
                daily_report_no=row['daily_report_no'],
                tablet_no=row['tablet_no'],
                left_total_1=row['left_total_1'],
                left_total_2=row['left_total_2'],
                left_total_3=row['left_total_3'],
                right_total_1=row['right_total_1'],
                right_total_2=row['right_total_2'],
            )
            records.append(record)
    return records


# ===== マッチング ロジック =====

def normalize_tablet_no(tablet_no: Optional[str]) -> Optional[str]:
    """タブレットNo を正規化"""
    if not tablet_no:
        return None
    # スペース・特殊文字の正規化
    normalized = tablet_no.replace(' ', '').replace('¶', 'it').lower()
    return normalized


def match_by_daily_report_no(extraction: ExtractionResult, records: List[SalesforceRecord]) -> Tuple[Optional[SalesforceRecord], List[SalesforceRecord]]:
    """マッチング① 日報DataNo で照合"""
    if not extraction.daily_report_no:
        return None, []

    matches = [r for r in records if r.daily_report_no == extraction.daily_report_no]
    if len(matches) == 1:
        return matches[0], matches
    elif len(matches) > 1:
        return None, matches  # 複数マッチ
    else:
        return None, []


def match_by_tablet_no(extraction: ExtractionResult, records: List[SalesforceRecord]) -> Tuple[Optional[SalesforceRecord], List[SalesforceRecord]]:
    """マッチング② タブレットNo で照合"""
    if not extraction.tablet_no:
        return None, []

    extraction_tab_norm = normalize_tablet_no(extraction.tablet_no)
    matches = []
    for r in records:
        record_tab_norm = normalize_tablet_no(r.tablet_no)
        if record_tab_norm == extraction_tab_norm:
            matches.append(r)

    if len(matches) == 1:
        return matches[0], matches
    elif len(matches) > 1:
        return None, matches  # 複数マッチ
    else:
        return None, []


def match_by_composite_key(extraction: ExtractionResult, records: List[SalesforceRecord]) -> Tuple[Optional[SalesforceRecord], List[SalesforceRecord]]:
    """マッチング③ 複合キー（日付+店舗名+氏名）で照合"""
    if not (extraction.date and extraction.store_name and extraction.staff_name):
        return None, []

    matches = [r for r in records
               if r.date == extraction.date
               and r.store_name == extraction.store_name
               and r.staff_name == extraction.staff_name]

    if len(matches) == 1:
        return matches[0], matches
    elif len(matches) > 1:
        return None, matches  # 複数マッチ
    else:
        return None, []


def reconcile(extraction: ExtractionResult, records: List[SalesforceRecord]) -> ReconciliationResult:
    """1件の抽出結果を照合"""

    matched_by = ""  # どのキーで見つけたか
    matched_record = None
    multiple_matches = []

    # ① 日報DataNo で照合
    matched_record, candidates = match_by_daily_report_no(extraction, records)
    if matched_record:
        matched_by = "日報DataNo"
    elif candidates:
        multiple_matches = candidates
        matched_by = "日報DataNo（複数候補）"

    # ② DataNo で見つからない場合、タブレットNo で照合
    if not matched_record and not multiple_matches:
        matched_record, candidates = match_by_tablet_no(extraction, records)
        if matched_record:
            matched_by = "タブレットNo"
        elif candidates:
            multiple_matches = candidates
            matched_by = "タブレットNo（複数候補）"

    # ③ それでも見つからない場合、複合キー で照合
    if not matched_record and not multiple_matches:
        matched_record, candidates = match_by_composite_key(extraction, records)
        if matched_record:
            matched_by = "複合キー（日付+店舗名+氏名）"
        elif candidates:
            multiple_matches = candidates
            matched_by = "複合キー（複数候補）"

    # ステータス判定
    status = ""
    differences = []
    review_reasons = []
    match_found = matched_record is not None and len(multiple_matches) == 0

    if not matched_record and not multiple_matches:
        # CSV行が見つからない
        status = "要確認"
        review_reasons.append("CSV内に対応するレコードが見つかりません")
        matched_by = "見つかりませんでした"
    elif multiple_matches:
        # 複数マッチ
        status = "要確認"
        review_reasons.append(f"複数の候補レコードが見つかりました（{len(multiple_matches)}件）")
    else:
        # CSV行が見つかった → 全項目比較
        if extraction.needs_review:
            # 読取値が不明瞭
            status = "要確認"
            review_reasons.append("Vision抽出結果に不明瞭な項目があります（needs_review=True）")
        else:
            # 全項目で差分チェック
            item_diffs = []

            # 日報DataNo
            if (extraction.daily_report_no or "") != (matched_record.daily_report_no or ""):
                item_diffs.append(f"日報DataNo: 帳票={extraction.daily_report_no or '未読取'}, CSV={matched_record.daily_report_no}")

            # タブレットNo
            extraction_tab_norm = normalize_tablet_no(extraction.tablet_no)
            record_tab_norm = normalize_tablet_no(matched_record.tablet_no)
            if extraction_tab_norm != record_tab_norm:
                item_diffs.append(f"タブレットNo: 帳票={extraction.tablet_no or '未読取'}, CSV={matched_record.tablet_no}")

            # 日付
            if (extraction.date or "") != (matched_record.date or ""):
                item_diffs.append(f"日付: 帳票={extraction.date or '未読取'}, CSV={matched_record.date}")

            # 店舗名
            if (extraction.store_name or "") != (matched_record.store_name or ""):
                item_diffs.append(f"店舗名: 帳票={extraction.store_name or '未読取'}, CSV={matched_record.store_name}")

            # 氏名
            if (extraction.staff_name or "") != (matched_record.staff_name or ""):
                item_diffs.append(f"氏名: 帳票={extraction.staff_name or '未読取'}, CSV={matched_record.staff_name}")

            # 左下合計欄
            if extraction.left_totals != matched_record.get_left_totals():
                item_diffs.append(f"左下合計欄: 帳票={'/'.join(extraction.left_totals) if extraction.left_totals else '未読取'}, CSV={'/'.join(matched_record.get_left_totals())}")

            # 右下合計欄
            if extraction.right_totals != matched_record.get_right_totals():
                item_diffs.append(f"右下合計欄: 帳票={'/'.join(extraction.right_totals) if extraction.right_totals else '未読取'}, CSV={'/'.join(matched_record.get_right_totals())}")

            if item_diffs:
                status = "不一致"
                differences = item_diffs
            else:
                status = "一致"

    return ReconciliationResult(
        file_name=extraction.file_name,
        matching_key=matched_by,
        extraction=extraction,
        matched_record=matched_record,
        status=status,
        differences=differences,
        review_reasons=review_reasons
    )


# ===== 結果出力 =====

def output_reconciliation_csv(results: List[ReconciliationResult], output_path: str):
    """照合結果をCSV出力"""
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'file_name',
            'matching_key',
            '帳票_date',
            '帳票_store_name',
            '帳票_staff_name',
            '帳票_daily_report_no',
            '帳票_tablet_no',
            '帳票_left_totals',
            '帳票_right_totals',
            'CSV_date',
            'CSV_store_name',
            'CSV_staff_name',
            'CSV_daily_report_no',
            'CSV_tablet_no',
            'CSV_left_totals',
            'CSV_right_totals',
            'status',
            'differences',
            'review_reasons'
        ])
        writer.writeheader()

        for result in results:
            row = {
                'file_name': result.file_name,
                'matching_key': result.matching_key,
                '帳票_date': result.extraction.date or '',
                '帳票_store_name': result.extraction.store_name or '',
                '帳票_staff_name': result.extraction.staff_name or '',
                '帳票_daily_report_no': result.extraction.daily_report_no or '',
                '帳票_tablet_no': result.extraction.tablet_no or '',
                '帳票_left_totals': '/'.join(result.extraction.left_totals) if result.extraction.left_totals else '',
                '帳票_right_totals': '/'.join(result.extraction.right_totals) if result.extraction.right_totals else '',
                'CSV_date': result.matched_record.date if result.matched_record else '',
                'CSV_store_name': result.matched_record.store_name if result.matched_record else '',
                'CSV_staff_name': result.matched_record.staff_name if result.matched_record else '',
                'CSV_daily_report_no': result.matched_record.daily_report_no if result.matched_record else '',
                'CSV_tablet_no': result.matched_record.tablet_no if result.matched_record else '',
                'CSV_left_totals': '/'.join(result.matched_record.get_left_totals()) if result.matched_record else '',
                'CSV_right_totals': '/'.join(result.matched_record.get_right_totals()) if result.matched_record else '',
                'status': result.status,
                'differences': ' | '.join(result.differences) if result.differences else '',
                'review_reasons': ' | '.join(result.review_reasons) if result.review_reasons else ''
            }
            writer.writerow(row)


def output_reconciliation_report(results: List[ReconciliationResult], output_path: str):
    """照合結果をMarkdownレポート出力"""

    # 統計集計
    total = len(results)
    matched_count = sum(1 for r in results if r.status in ["一致", "不一致"])
    unmached_count = sum(1 for r in results if r.status == "要確認")
    identical_count = sum(1 for r in results if r.status == "一致")
    different_count = sum(1 for r in results if r.status == "不一致")

    report = f"""# 合成サンプルPDF × Salesforce CSV 照合レポート

## 📋 概要

合成サンプルPDF 15件を Vision API で抽出後、Salesforce想定CSVとの照合を実施。

**処理日**: 2026-05-06
**対象件数**: {total} 件
**処理方式**: 3段階マッチング（日報DataNo → タブレットNo → 複合キー）

---

## 📊 照合結果サマリー

| ステータス | 件数 | 割合 |
|-----------|------|------|
| **一致** | {identical_count} | {identical_count/total*100:.1f}% |
| **不一致** | {different_count} | {different_count/total*100:.1f}% |
| **要確認** | {unmached_count} | {unmached_count/total*100:.1f}% |
| **計** | **{total}** | **100%** |

### マッチング成功

- **マッチング成功**: {matched_count} / {total} 件（{matched_count/total*100:.1f}%）
- **マッチング失敗（要確認）**: {unmached_count} / {total} 件（{unmached_count/total*100:.1f}%）

---

## 📝 詳細結果

"""

    # ステータス別に表示
    for status in ["一致", "不一致", "要確認"]:
        status_results = [r for r in results if r.status == status]
        if not status_results:
            continue

        report += f"\n### {status}（{len(status_results)}件）\n\n"

        for i, result in enumerate(status_results, 1):
            report += f"#### {i}. {result.file_name}\n\n"
            report += f"**マッチングキー**: {result.matching_key}  \n"
            report += f"**ステータス**: {result.status}  \n\n"

            report += f"**帳票側（Vision API抽出値）**\n"
            report += f"- 日付: {result.extraction.date or '未読取'}  \n"
            report += f"- 店舗名: {result.extraction.store_name or '未読取'}  \n"
            report += f"- 氏名: {result.extraction.staff_name or '未読取'}  \n"
            report += f"- 日報DataNo: {result.extraction.daily_report_no or '未読取'}  \n"
            report += f"- タブレットNo: {result.extraction.tablet_no or '未読取'}  \n"
            report += f"- 左下合計: {'/'.join(result.extraction.left_totals) if result.extraction.left_totals else '未読取'}  \n"
            report += f"- 右下合計: {'/'.join(result.extraction.right_totals) if result.extraction.right_totals else '未読取'}  \n\n"

            if result.matched_record:
                report += f"**CSV側（期待値）**\n"
                report += f"- 日付: {result.matched_record.date}  \n"
                report += f"- 店舗名: {result.matched_record.store_name}  \n"
                report += f"- 氏名: {result.matched_record.staff_name}  \n"
                report += f"- 日報DataNo: {result.matched_record.daily_report_no}  \n"
                report += f"- タブレットNo: {result.matched_record.tablet_no}  \n"
                report += f"- 左下合計: {'/'.join(result.matched_record.get_left_totals())}  \n"
                report += f"- 右下合計: {'/'.join(result.matched_record.get_right_totals())}  \n\n"
            else:
                report += f"**CSV側**: マッチなし  \n\n"

            if result.differences:
                report += f"**差分内容**\n"
                for diff in result.differences:
                    report += f"- {diff}  \n"
                report += "\n"

            if result.review_reasons:
                report += f"**要確認理由**\n"
                for reason in result.review_reasons:
                    report += f"- {reason}  \n"
                report += "\n"

            report += "\n"

    report += f"""---

## 🔍 マッチング方式の詳細

### 3段階マッチング

1. **① 日報DataNo で照合**
   - Vision API抽出の日報DataNo と Salesforce CSV の日報DataNo を完全一致で比較
   - 1件見つかった場合：そのレコードを確定
   - 複数件見つかった場合：要確認（複数候補）
   - 見つからない場合：次段階へ

2. **② タブレットNo で照合**
   - タブレットNo を正規化（スペース削除、特殊文字正規化）して比較
   - 同様に1件 / 複数 / なし で判定

3. **③ 複合キーで照合**
   - 日付 + 店舗名 + 氏名 の3項目の組み合わせで照合
   - 最後の手段。実装用に、複合キーは「日付・店舗名・氏名」を全て正確に読み取ることが条件

### ステータス判定ルール

| ステータス | 条件 |
|----------|------|
| **一致** | マッチング成功 ∧ needs_review=False ∧ 合計欄差分なし |
| **不一致** | マッチング成功 ∧ needs_review=False ∧ 左右合計欄に差分あり |
| **要確認** | マッチング失敗 ∨ needs_review=True ∨ 複数マッチ ∨ 読み取り値が空欄 |

---

## ⚠️ 重要な注記

### データについて

**本結果は合成サンプルPDFによる検証です**

- 合成サンプル 15件では、日付・店舗名・氏名・日報DataNo・タブレットNo・左右合計欄の主要7項目について、抽出成功を確認
- **この結果は合成サンプルによる検証であり、実帳票・実FAX画質での精度保証ではない**
- 実帳票での精度は別途検証が必要

### 今後のアクション

- **次フェーズ**: 実帳票サンプル複数枚と Salesforce 実CSVにより検証が必要
- **Streamlit UI**: 照合ロジックが通った後で組み込み推奨

---

## 📂 関連ファイル

- `synthetic_extraction_results.csv` - Vision API抽出結果
- `salesforce_sample.csv` - Salesforce想定CSV（テスト用）
- `reconciliation_results.csv` - 照合結果（詳細）
- `reconciliation_report.md` - 本レポート

---

**作成日**: 2026-05-06
**バージョン**: 1.0
**ステータス**: ✅ 合成サンプル照合完了
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

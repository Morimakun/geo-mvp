"""
FAX帳票 × Salesforce CSV 照合ロジック

照合エンジン（CSV読込 → マッチング → ステータス判定 → 結果出力）
このモジュールは test_reconciliation.py と app.py の両方から import される
"""

import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import pandas as pd
from datetime import datetime


# ===== データ構造 =====

@dataclass
class ExtractionResult:
    """帳票読み取り結果

    新方針（2026-05-29 修正版）：
    - daily_report_no / tablet_no は「識別情報・証跡」
    - PDF右側の商材別実績、左下/右下の手書き集計を抽出
    - CSV側との照合キーは「日付 + 法人・店舗コード + 集計値」
    """
    file_name: str
    date: Optional[str]

    # 識別情報・証跡（CSVとの直接照合キーではない）
    daily_report_no: Optional[str]  # 帳票を特定するための参照情報
    tablet_no: Optional[str]        # デバイスを特定するための参照情報

    # 店舗情報（CSV側の法人・店舗(取扱コード) と紐づけるため）
    store_code: Optional[str]  # PDFから読み取った店舗コード（見読範囲で）
    store_name: Optional[str]  # 店舗名（見読範囲で）
    staff_name: Optional[str]  # 担当者名（見読範囲で）

    # 集計値（PDF右側の商材別実績表）
    # キー：商材名、値：実績数
    right_side_data: Dict[str, str] = None  # {"eo光": "20", "eo光電話": "15", ...}

    # 手書き集計欄（PDF左下）
    left_bottom_totals: Dict[str, str] = None  # {"成約": "22", "来店": "50", ...}

    # 手書き集計欄（PDF右下）
    right_bottom_totals: Dict[str, str] = None  # {"全体成約": "22", "全体人員": "5", ...}

    # 旧フォーマットとの互換性（廃止予定）
    left_totals: List[str] = None   # ["29", "9", "3"] or [] (deprecated)
    right_totals: List[str] = None  # ["27", "5"] or [] (deprecated)

    needs_review: bool = False

    def __post_init__(self):
        """デフォルト値の初期化"""
        if self.right_side_data is None:
            self.right_side_data = {}
        if self.left_bottom_totals is None:
            self.left_bottom_totals = {}
        if self.right_bottom_totals is None:
            self.right_bottom_totals = {}
        if self.left_totals is None:
            self.left_totals = []
        if self.right_totals is None:
            self.right_totals = []


@dataclass
class SalesforceRecord:
    """Salesforce / 実績レポート CSV レコード

    実CSVは販売実績レポート形式で、旧想定の日報明細CSVではない。
    そのため、日報DataNo / タブレットNo は存在しないことを前提に対応する。
    """
    # 基本情報
    csv_date: Optional[str]           # CSV側の日付列（日付、date など）
    store_code: Optional[str]         # 法人・店舗(取扱コード)
    company_name: Optional[str]       # 委託会社名
    staff_name: Optional[str] = ""    # 担当者名（見つからない場合は空）
    daily_report_no: Optional[str] = ""  # 日報DataNo（見つからない場合は空）
    tablet_no: Optional[str] = ""     # タブレットNo（見つからない場合は空）

    # 集計値（実CSVから抽出可能な列）
    total_new_contracts: Optional[str] = None      # 成約総数（新規）
    htmz_contracts: Optional[str] = None           # HT/Mz成約数
    mt_contracts: Optional[str] = None             # MT成約数
    existing_users: Optional[str] = None           # 既存ユーザー数
    overall_htmz_total: Optional[str] = None       # 全体：HT/MZ成約数計
    overall_mt_total: Optional[str] = None         # 全体：MT成約数計
    overall_existing_total: Optional[str] = None   # 全体：既存サービス数計

    # メモ・追跡情報
    memo: str = ""                    # 列なし情報など
    raw_row: Dict = None              # 元行データ（デバッグ用）

    def __post_init__(self):
        """デフォルト値の初期化"""
        if self.raw_row is None:
            self.raw_row = {}
        # デフォルト値の確保
        if self.daily_report_no is None:
            self.daily_report_no = ""
        if self.tablet_no is None:
            self.tablet_no = ""
        if self.staff_name is None:
            self.staff_name = ""


@dataclass
class ReconciliationResult:
    """照合結果

    新方針（2026-05-29 修正版）：
    - 照合キー：「日付 + 法人・店舗(取扱コード) + 委託会社名 + 集計値」
    - 日報DataNo / タブレットNo は識別情報として保持
    - CSVの7項目の先方確認が完了するまで「要確認」が標準
    """
    file_name: str

    # 照合方式の明記
    matching_strategy: str = "日付+法人・店舗(取扱コード)+集計値ベース"

    extraction: ExtractionResult = None
    matched_record: Optional[SalesforceRecord] = None

    # ステータス判定
    status: str = "要確認"  # "一致" | "不一致" | "要確認"

    # 照合詳細
    differences: List[str] = None
    review_reasons: List[str] = None

    # 新規フィールド：PDF側の識別情報を記録
    extraction_details: Dict[str, Any] = None  # {
    #   "daily_report_no": "...",
    #   "tablet_no": "...",
    #   "store_code": "...",
    #   "right_side_data": {...},
    #   "left_bottom_totals": {...},
    #   "right_bottom_totals": {...}
    # }

    # 先方確認待ち項目
    pending_confirmations: List[str] = None  # [
    #   "Q1: このCSVが照合対象ファイルとして正しいか",
    #   "Q4: PDF右側の商材別表はCSVのどの列に対応するか",
    #   ...
    # ]

    def __post_init__(self):
        """デフォルト値の初期化"""
        if self.differences is None:
            self.differences = []
        if self.review_reasons is None:
            self.review_reasons = []
        if self.extraction_details is None:
            self.extraction_details = {}
        if self.pending_confirmations is None:
            self.pending_confirmations = []


# ===== 汎用列検出・日付処理 =====

def find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """
    DataFrame から複数の候補列から最初にマッチする列を検出

    Args:
        df: pandas DataFrame
        candidates: 検出対象の列名候補リスト（優先順）

    Returns:
        見つかった列名、見つからない場合は None
    """
    for col in candidates:
        if col in df.columns:
            return col
    return None


def find_date_column(df: pd.DataFrame) -> Optional[str]:
    """
    DataFrame から日付列を検出する関数

    複数の言語対応：日本語の「日付」、英語の「date」など

    Args:
        df: pandas DataFrame

    Returns:
        検出した日付列名、見つからない場合は None
    """
    # 候補列の優先順
    candidates = ["日付", "date", "Date", "DATE", "営業日", "対象日", "年月日"]

    for col in candidates:
        if col in df.columns:
            return col

    # 見つからない場合
    return None


def normalize_date(value: Optional[str]) -> Optional[str]:
    """
    日付文字列を YYYY-MM-DD 形式に正規化

    対応形式：
    - 2026/05/17 → 2026-05-17
    - 2026-05-17 → 2026-05-17
    - 2026年5月17日 → 2026-05-17
    - 2026/5/17 → 2026-05-17
    - 2026-5-17 → 2026-05-17

    Args:
        value: 日付文字列

    Returns:
        正規化された日付（YYYY-MM-DD形式）、または None
    """
    if not value or not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    # Pattern 1: スラッシュ形式 (2026/05/17 または 2026/5/17)
    match = re.match(r'(\d{4})[/\-\s]*(\d{1,2})[/\-\s]*(\d{1,2})', value)
    if match:
        try:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            # 妥当性チェック
            if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        except:
            pass

    # Pattern 2: 日本語形式 (2026年5月17日)
    match = re.match(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', value)
    if match:
        try:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if 1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"
        except:
            pass

    return None


def filter_csv_by_business_date(df: pd.DataFrame, target_business_date: str, date_column: Optional[str] = None) -> Tuple[pd.DataFrame, Optional[str], Optional[str]]:
    """
    CSV DataFrame を対象営業日でフィルタ

    Args:
        df: CSV を読み込んだ DataFrame
        target_business_date: 対象営業日（例：2026-05-17）
        date_column: 日付列の名前（デフォルト：None -> 自動検出）

    Returns:
        (フィルタされた DataFrame, エラーメッセージまたはNone, 検出した日付列名)
        - エラーメッセージはフィルタ対象行なし時に返される
        - 日付列名は検出時に返される
    """
    # 日付列を自動検出
    if date_column is None:
        date_column = find_date_column(df)

    if date_column is None:
        return pd.DataFrame(), "日付列が見つかりません", None

    if date_column not in df.columns:
        return pd.DataFrame(), f"日付列 '{date_column}' が見つかりません", None

    # 対象営業日を正規化
    normalized_target = normalize_date(target_business_date)
    if not normalized_target:
        return pd.DataFrame(), f"不正な日付形式: {target_business_date}", date_column

    # CSV内の日付を正規化してフィルタ
    df_copy = df.copy()
    df_copy['_normalized_date'] = df_copy[date_column].apply(normalize_date)

    filtered = df_copy[df_copy['_normalized_date'] == normalized_target].drop(columns=['_normalized_date'])

    if len(filtered) == 0:
        return pd.DataFrame(), f"対象営業日 {target_business_date} に該当する行がありません（検出日付: {df[date_column].unique().tolist()}）", date_column

    return filtered, None, date_column


# ===== CSV読込 =====

def load_extraction_results(csv_path: str) -> List[ExtractionResult]:
    """帳票読み取り結果を読込"""
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


def load_salesforce_csv(csv_path: str, encoding: str = 'utf-8') -> List[SalesforceRecord]:
    """
    Salesforce / 実績レポート CSV を読込

    実CSVは販売実績レポート形式で、旧想定の日報明細CSVではない。
    列検出により、存在しない列はエラーにせず、空欄またはメモとして扱う。

    Args:
        csv_path: CSV ファイルパス
        encoding: CSV エンコーディング（デフォルト：utf-8）

    Returns:
        SalesforceRecord リスト
    """
    records = []

    # 複数エンコーディングを試す
    encodings_to_try = [encoding, 'cp932', 'shift_jis', 'utf-8-sig', 'utf-8']
    df_temp = None

    for enc in encodings_to_try:
        try:
            df_temp = pd.read_csv(csv_path, encoding=enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if df_temp is None:
        raise ValueError(f"Unable to read CSV with any encoding: {csv_path}")

    # DictReader 用のエンコーディングを検出した encoding で開く
    actual_encoding = None
    for enc in encodings_to_try:
        try:
            with open(csv_path, 'r', encoding=enc) as f:
                reader = csv.DictReader(f)
                _ = next(reader, None)  # 最初の行を読んでみる
                actual_encoding = enc
                break
        except (UnicodeDecodeError, LookupError):
            continue

    if actual_encoding is None:
        raise ValueError(f"Unable to read CSV with any encoding: {csv_path}")

    # 本読み込み
    with open(csv_path, 'r', encoding=actual_encoding) as f:
        reader = csv.DictReader(f)

        # 列検出：候補リストから最初にマッチする列を使用
        date_col = find_column(df_temp, ["日付", "date", "Date", "営業日", "対象日"])
        store_code_col = find_column(df_temp, ["法人・店舗(取扱コード)", "取扱コード", "店舗コード", "store_code", "store_id"])
        company_name_col = find_column(df_temp, ["委託会社名", "店舗名", "store_name", "company_name"])
        staff_name_col = find_column(df_temp, ["担当者名", "スタッフ名", "staff_name"])
        daily_report_no_col = find_column(df_temp, ["日報DataNo", "日報データNo", "daily_report_no"])
        tablet_no_col = find_column(df_temp, ["タブレットNo", "tablet_no", "Tab No"])

        # 集計値列の検出
        total_contracts_col = find_column(df_temp, ["成約総数（新規）", "成約総数"])
        htmz_col = find_column(df_temp, ["HT/Mz（電話+テレビ含む）成約数", "HT/Mz成約数"])
        mt_col = find_column(df_temp, ["MT成約数"])
        existing_users_col = find_column(df_temp, ["既存ユーザー数"])
        overall_htmz_col = find_column(df_temp, ["全体：HT/MZ（電話＋テレビ含む）成約数計", "全体：HT/MZ成約数計"])
        overall_mt_col = find_column(df_temp, ["全体：MT成約数計"])
        overall_existing_col = find_column(df_temp, ["全体：既存サービス数計"])

        # メモ作成：見つからない列を記録
        missing_cols = []
        if daily_report_no_col is None:
            missing_cols.append("日報DataNo")
        if tablet_no_col is None:
            missing_cols.append("タブレットNo")

        memo_base = ""
        if missing_cols:
            memo_base = f"CSVに{'/'.join(missing_cols)}列なし。PDF側識別情報として保持。"

        # 行を読込
        for idx, row in enumerate(reader):
            # 列の値を取得（存在しない場合は None）
            csv_date = row.get(date_col) if date_col else None
            store_code = row.get(store_code_col) if store_code_col else None
            company_name = row.get(company_name_col) if company_name_col else None
            staff_name = row.get(staff_name_col) if staff_name_col else ""
            daily_report_no = row.get(daily_report_no_col) if daily_report_no_col else ""
            tablet_no = row.get(tablet_no_col) if tablet_no_col else ""

            # 集計値を取得
            total_contracts = row.get(total_contracts_col) if total_contracts_col else None
            htmz = row.get(htmz_col) if htmz_col else None
            mt = row.get(mt_col) if mt_col else None
            existing_users = row.get(existing_users_col) if existing_users_col else None
            overall_htmz = row.get(overall_htmz_col) if overall_htmz_col else None
            overall_mt = row.get(overall_mt_col) if overall_mt_col else None
            overall_existing = row.get(overall_existing_col) if overall_existing_col else None

            record = SalesforceRecord(
                csv_date=csv_date,
                store_code=store_code,
                company_name=company_name,
                staff_name=staff_name,
                daily_report_no=daily_report_no,
                tablet_no=tablet_no,
                total_new_contracts=total_contracts,
                htmz_contracts=htmz,
                mt_contracts=mt,
                existing_users=existing_users,
                overall_htmz_total=overall_htmz,
                overall_mt_total=overall_mt,
                overall_existing_total=overall_existing,
                memo=memo_base,
                raw_row=dict(row)
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
            review_reasons.append("帳票合計欄の読み取り未対応または未取得のため、確認が必要です")
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

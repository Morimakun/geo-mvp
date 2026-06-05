# Phase 3 実装計画：PDF読取値とCSV指定列の比較判定

## 概要

Phase 2 で取得した CSV 候補行に対して、PDF から抽出した数値と CSV の対応列を比較し、一致 / 不一致 / 要確認を判定する。Phase 1, 2 の結果を統合して最終的なマッチング判定を行う。

---

## 1. 現在の出力構造確認

### 1.1 reconcile_pdf_with_csv() の戻り値構造

**現状の項目** (reconciliation_phase1.py より):

```python
{
    # ステータス（最終判定）
    'status': 'match' | 'mismatch' | 'review',
    
    # CSV候補関連
    'csv_record_idx': int or None,           # CSV行インデックス
    'candidates': [{'idx': int, 'score': float, ...}, ...],
    'best_match': {'idx': int, 'score': float, ...} or None,
    
    # スコア関連
    'score': float,                          # 総合スコア
    'match_count': int,                      # 一致項目数
    'diff_count': int,                       # 不一致項目数
    'unreadable_count': int,                 # 読取不可項目数
    
    # 項目詳細
    'matched_items': [str, ...],            # 一致した項目名リスト
    'diff_items': [str, ...],               # 不一致の項目名（PDF:X vs CSV:Y形式）
    'unreadable_items': [str, ...],         # 読取不可の項目名リスト
    
    # 店舗・スタッフ情報
    'store_code': str,
    'store_name': str,
    'staff_name': str or None,
    'tablet_no': str or None,
    'data_no': str or None,
    
    # ログ
    'warnings': [str, ...],
    'review_reasons': [str, ...]
}
```

### 1.2 PDF読取結果の構造（pdf_record）

```python
{
    'page_no': int,                          # ページ番号
    'store_name': str or None,               # PDF から抽出した店舗名
    'staff_name': str or None,               # PDF から抽出したスタッフ名
    'tablet_no': str or None,                # タブレット番号
    'data_no': str or None,                  # データ番号（日報 No）
    'mapped_values': {
        'HH': 0,           # csv_column_code -> PDF値
        'HI': 1,
        'GS': 'uncertain',  # 正の字途中形
        'GT': 1,
        ...
    }
}
```

### 1.3 Phase 2 で追加された項目

```python
# Phase 2 で追加
'pdf_page_number': int,
'pdf_date': str,                    # YYYY/MM/DD
'pdf_store_name': str,
'mapped_store_code': str,
'store_code_mapping_status': str,   # exact_match | partial_match | not_found
'match_status': str,                # candidate_found | no_csv_candidate | multiple_csv_candidates
'csv_candidate_count': int,
'csv_candidate_rows': [...]
```

---

## 2. PDF読取値とCSV比較に使える項目の整理

### 2.1 PDF側：mapped_values の構造

```python
mapped_values = {
    'HH': 0,              # ✅ 数値（確実）
    'HI': 5,              # ✅ 数値（確実）
    'GS': 'uncertain',    # ⚠️ uncertain（正の字途中形）
    'GT': None,           # ⚠️ null（読めなかった）
    'JJ': 2,              # ✅ 数値（確実）
    ...
}
```

**値のパターン**:
- `int` / `float`: 確実な数値
- `'uncertain'`: 正の字の途中形（確定されていない）
- `None`: 読取不可 / 空欄
- `'5'` (文字列): 確実な数値（文字列型）

### 2.2 CSV側：行全体（pd.Series）の構造

```python
csv_row.iloc[0]      # 営業日
csv_row.iloc[1]      # 何か
...
csv_row.iloc[280]    # 店舗コード（JU）
csv_row.iloc[215]    # ネット追加(HH)   ← CSV列番号は 216（1-indexed）
csv_row.iloc[216]    # ネット追加 別列
...
```

**csv_column_number** の意味：
- pdf_csv_field_mapping.csv の「csv_column_number」
- Excelスタイルの列番号（1-indexed）
- 使用時は `csv_row.iloc[csv_column_number - 1]` で取得

---

## 3. pdf_csv_field_mapping.csv の読み込み設計

### 3.1 現在の利用状況

**reconciliation_phase1.py の __init__ より**:

```python
# 確定済み項目のみを抽出
confirmed = mapping_table[mapping_table['mapping_status'] == 'confirmed'].copy()

# needs_confirmation が false のもの
confirmed = confirmed[
    (confirmed['needs_confirmation'].astype(str).str.lower() == 'false') |
    (confirmed['needs_confirmation'] == False)
]

# csv_column_code が存在する
confirmed = confirmed[confirmed['csv_column_code'].notna()]
confirmed = confirmed[confirmed['csv_column_code'].astype(str).str.strip() != '']

# 除外キーワード
exclude_keywords = ['未使用', '要確認', '名称確認待ち', '運用確認要', '正式名称確認要']
for keyword in exclude_keywords:
    confirmed = confirmed[~confirmed['memo'].astype(str).str.contains(keyword, na=False)]

self.confirmed_mapping = confirmed
```

**結果**: `self.confirmed_mapping` に確定済み項目のみが格納される

### 3.2 Phase 3 で必要な情報

```python
# Phase 3 での利用例
for idx, mapping_row in self.confirmed_mapping.iterrows():
    item_name = mapping_row.get('fax_item_name')         # 例: 'ネット追加(HH)'
    csv_column_code = mapping_row.get('csv_column_code') # 例: 'HH'
    csv_column_number = mapping_row.get('csv_column_number')  # 例: 216
    pdf_column_code = csv_column_code  # Phase 2 で使用される
```

### 3.3 読み込み設計

**既存**:
- エンジン初期化時に `self.confirmed_mapping` に確定済み項目が格納される
- ✅ Phase 3 で追加実装の負担なし

**注意点**:
- `mapping_status=confirmed` でも、needs_confirmation=true なら除外
- csv_column_code が空欄なら除外
- memo に除外キーワードが含まれていても除外

---

## 4. 比較対象にする条件定義

### 4.1 比較対象を決定するフロー

```
Step 1: self.confirmed_mapping から項目を取得
    ↓ (すでにフィルタ済み)
    ✅ mapping_status = 'confirmed'
    ✅ needs_confirmation = false
    ✅ csv_column_code が存在
    
Step 2: PDF側の値を確認
    pdf_value = pdf_record['mapped_values'].get(csv_column_code)
    
    if pdf_value is None:
        → 比較対象外（「読取不可」として count）
        → unreadable_items に追加
        
    elif pdf_value == 'uncertain':
        → 比較対象外（「要確認」として count）
        → review_reasons に追加
        
    elif isinstance(pdf_value, (int, float)):
        → 比較対象 ✅
        → CSV列と比較
        
    elif isinstance(pdf_value, str) and pdf_value.isdigit():
        → 比較対象 ✅
        → int に変換して比較

Step 3: CSV側の値を確認
    csv_value = csv_row.iloc[csv_column_number - 1]
    
    if csv_value is None:
        → null として count
        → diff_items に記録
        
    else:
        → 数値として解釈
```

### 4.2 比較対象条件チェックリスト

```
[✅] self.confirmed_mapping に含まれている
[✅] mapping_status = 'confirmed'
[✅] needs_confirmation = false または not present
[✅] csv_column_code != None and != ''
[✅] PDF側: pdf_value が数値または 'uncertain' / None
[✅] CSV側: csv_value が取得可能
[✗] 除外: pdf_value = 'uncertain' (比較対象外だが unreadable_count に含める)
[✗] 除外: pdf_value = None (比較対象外だが unreadable_count に含める)
```

### 4.3 5G → 10G 合算対応

**ポリシー**: 5G → 10G は合算しない（別項目として扱う）

```python
# 例：fax_item_name が「5G」「10G」の場合
# → 分別したまま比較する（合算は Phase 3 では行わない）

# CSV側での参考情報
# - 「5G」と「10G」は異なる csv_column_code かもしれない
# - または同じ csv_column_number で異なる logic が必要かもしれない
# → memo に特記がある場合のみ対応（将来仕様）
```

---

## 5. 比較結果の出力形式設計

### 5.1 詳細比較結果（field_comparisons）

```python
field_comparisons = [
    {
        # 項目情報
        'fax_item_name': 'ネット追加(HH)',      # UI 表示用
        'csv_column_code': 'HH',                 # マッピング識別子
        'csv_column_number': 216,                # CSV列番号（参考）
        
        # 値
        'pdf_value': 0,                         # PDF から抽出
        'csv_value': 0,                         # CSV から取得
        'pdf_value_status': 'confirmed',        # 'confirmed' | 'uncertain' | 'null'
        'csv_value_status': 'confirmed',        # 'confirmed' | 'null'
        
        # 比較結果
        'comparison_status': 'match',           # 'match' | 'diff' | 'uncertain' | 'unreadable'
        'match_type': 'exact',                  # 'exact' | 'partial' | 'cannot_compare'
        'reason': 'Both values are 0',          # 詳細な理由
        
        # スコア
        'comparison_score': 10,                 # match: +10, diff: -5, uncertain/unreadable: 0
    },
    {
        'fax_item_name': '地デジBS',
        'csv_column_code': 'GT',
        'csv_column_number': 201,
        'pdf_value': 'uncertain',
        'csv_value': 1,
        'pdf_value_status': 'uncertain',
        'csv_value_status': 'confirmed',
        'comparison_status': 'uncertain',
        'match_type': 'cannot_compare',
        'reason': 'PDF value is uncertain (tally mark途中形)',
        'comparison_score': 0,
    },
    ...
]
```

### 5.2 集計結果

```python
# 結果の集計
field_comparison_summary = {
    'total_items': 42,                         # 比較対象項目数
    'matched_items': 38,                       # 完全一致
    'diff_items': 2,                           # 不一致
    'uncertain_items': 1,                      # 確実でない（正の字途中形）
    'unreadable_items': 1,                     # 読取不可（null）
    
    # スコア
    'base_score': 38 * 10 + 2 * (-5) + 1 * 0 + 1 * 0 = 370,  # 比較ベーススコア
    'comparison_match_rate': 38 / 42 = 0.905,               # 一致率
    
    # ステータス判定
    'phase3_status': 'match' | 'mismatch' | 'review',
}
```

### 5.3 最終結果オブジェクト（拡張）

```python
# 既存の結果に Phase 3 項目を追加
result = {
    # Phase 1, 2 既存
    'status': 'match' | 'mismatch' | 'review',
    'store_code': str,
    'csv_record_idx': int or None,
    ...
    
    # Phase 3 新規
    'field_comparisons': [...],                 # 詳細比較結果
    'field_comparison_summary': {...},          # 集計結果
    'comparison_match_rate': 0.905,             # 一致率
    'phase3_status': 'match' | 'mismatch' | 'review',  # Phase 3 判定
    'phase3_score': 370,                        # Phase 3 スコア
    'phase3_review_reasons': [str, ...],        # Phase 3 の確認理由
}
```

---

## 6. 判定ルール設計

### 6.1 Phase 3 判定フロー

```
【Input】
- csv_match_result from Phase 2
  * match_status: 'candidate_found' | 'no_csv_candidate' | 'multiple_csv_candidates'
  * candidates_df: 候補行（1件または複数件）
  
- pdf_record
  * mapped_values: {csv_column_code: pdf_value, ...}

【Step 1】: CSV候補の状況確認

if csv_match_result['match_status'] == 'no_csv_candidate':
    → return {'phase3_status': 'review', 'reason': 'No CSV candidates from Phase 2'}
    
if csv_match_result['match_status'] == 'multiple_csv_candidates':
    → 複数候補に対して各々で比較スコア計算
    → スコア最高の行を best_match に
    → スコア接近していれば phase3_status = 'review'

if csv_match_result['match_status'] == 'candidate_found':
    → 1行のみ、確実に比較可能

【Step 2】: field_comparisons を計算

for each csv_row in candidates_df:
    field_comparisons = _compare_fields(pdf_record, csv_row, self.confirmed_mapping)
    comparison_score = sum of all item scores
    
【Step 3】: 判定

一致条件（match）:
  - CSV候補 1件 AND
  - 全比較対象項目で一致 (diff_count = 0) AND
  - uncertain / unreadable が少ない（0～1程度）AND
  - スコア > threshold（例：350点）

不一致条件（mismatch）:
  - CSV候補 1件 AND
  - 不一致項目が複数存在 (diff_count > 0) AND
  - スコア < threshold

要確認条件（review）:
  - CSV候補 0件 OR
  - CSV候補が複数 AND 最高スコアが接近 OR
  - 一致項目と不一致項目が混在 OR
  - uncertain / unreadable が多い (> 3) OR
  - スコアが threshold 付近（±50点以内）
```

### 6.2 スコア計算ルール

```python
# 項目ごとのスコア
score_per_item = {
    'match': +10,                  # 完全一致
    'diff': -5,                    # 不一致
    'uncertain': 0,                # 正の字途中形
    'unreadable': 0,               # 読取不可 / null
}

# 基本スコア
base_score = sum of all item scores

# ボーナス
bonus_store = 200 * store_match_confidence      # Phase 1
bonus_staff = 2 if pdf_staff in master else 0  # 既存
bonus_date = 50 if date_match else 0           # Phase 2

# 総合スコア（Phase 3 対象）
comparison_score = base_score + bonus_store + bonus_staff + bonus_date
```

### 6.3 複数CSV候補での候補絞り込み

```python
【複数候補がある場合】

candidates_with_scores = []
for idx, csv_row in candidates_df.iterrows():
    score = _compare_fields_and_score(pdf_record, csv_row)
    candidates_with_scores.append({'csv_idx': idx, 'score': score, 'row': csv_row})

candidates_with_scores.sort(key=lambda x: x['score'], reverse=True)

best_match = candidates_with_scores[0]
second_best = candidates_with_scores[1] if len(candidates_with_scores) > 1 else None

score_diff = best_match['score'] - (second_best['score'] if second_best else 0)

if score_diff > 100:
    # 明確に最高スコアが優れている
    phase3_status = 'match' or 'mismatch' (その行の詳細比較による)
    
elif score_diff > 50:
    # スコア差がある程度ある
    phase3_status = 'review'  (候補絞り込みの確認が必要)
    
else:
    # スコアが接近している
    phase3_status = 'review'  (複数候補が同等のため確認が必要)
```

---

## 7. 正の字・手書き途中形の扱い

### 7.1 ポリシー

**ドキュメント参照**: `docs/TALLY_MARK_READING_POLICY.md`

```
Phase 1 (MVP): 確実な値のみ自動確定

自動確定する値:
  ✅ アラビア数字（1, 2, 3, ...）
  ✅ 完成した「正」（5本線）→ 5
  ✅ 明確な「一」（横線1本）→ 1
  ✅ 完全空欄 → null

要確認に回す値:
  ⚠️ T字形（横線+縦線）→ uncertain
  ⚠️ 途中形（3本線、4本線）→ uncertain
  ⚠️ 罫線と重複 → uncertain
  ⚠️ 不規則形 → uncertain
```

### 7.2 Phase 3 での扱い

```python
# PDF値が 'uncertain' の場合

if pdf_value == 'uncertain':
    → 比較対象外
    → field_comparisons で match_type = 'cannot_compare'
    → reason = "PDF value is uncertain (tally mark途中形)"
    → comparison_score = 0
    → uncertain_items count += 1
    
    # この行は「要確認」フラグが立つ
    review_reasons.append(f"Uncertain PDF value for {item_name}")
```

### 7.3 CSV側が null の場合

```python
# csv_value が null / empty の場合

if csv_value is None or csv_value == '' or pd.isna(csv_value):
    → 比較対象外
    → field_comparisons で match_type = 'cannot_compare'
    → reason = "CSV value is null"
    → comparison_score = 0
    → unreadable_items count += 1
    
    # この行は「要確認」フラグが立つ
    review_reasons.append(f"CSV value is null for {item_name}")
```

---

## 8. テスト方針

### 8.1 最小テストケース（10～15 件）

#### グループ1: 全項目一致（5 件）

1. **test_all_items_match**
   - PDF と CSV の全項目が一致
   - 期待: phase3_status = 'match'
   - 確認: matched_items > 0, diff_items = 0

2. **test_all_items_match_with_minor_unreadable**
   - 大部分一致、1項目 unreadable
   - 期待: phase3_status = 'match' (許容範囲内)
   - 確認: unreadable_count <= 1

3. **test_all_items_match_different_csv_rows**
   - CSV候補が1件で、項目全て一致
   - 期待: phase3_status = 'match'

4. **test_match_with_store_code_bonus**
   - 項目一致＋店舗一致ボーナス
   - 期待: phase3_status = 'match', score > 350

5. **test_match_with_date_bonus**
   - 項目一致＋日付一致ボーナス
   - 期待: phase3_status = 'match'

#### グループ2: 部分不一致（4 件）

6. **test_partial_mismatch_single_item**
   - 1項目のみ不一致、他は一致
   - 期待: phase3_status = 'mismatch' or 'review' (スコア低下)
   - 確認: diff_count = 1

7. **test_partial_mismatch_multiple_items**
   - 複数項目が不一致
   - 期待: phase3_status = 'mismatch'
   - 確認: diff_count >= 2, diff_items に詳細

8. **test_partial_mismatch_mixed_with_uncertain**
   - 不一致＋不確定項目が混在
   - 期待: phase3_status = 'review'
   - 確認: diff_count > 0, uncertain_count > 0

9. **test_mismatch_not_exceeding_threshold**
   - スコアが閾値未満
   - 期待: phase3_status = 'mismatch'
   - 確認: score < 200

#### グループ3: PDF値が不確定（3 件）

10. **test_pdf_value_uncertain**
    - PDF値が 'uncertain' （正の字途中形）
    - 期待: 比較対象外として処理
    - 確認: uncertain_items count

11. **test_pdf_value_null**
    - PDF値が None / 読取不可
    - 期待: unreadable_items に追加
    - 確認: unreadable_count

12. **test_pdf_values_mostly_uncertain**
    - PDF値の大部分が 'uncertain'
    - 期待: phase3_status = 'review' (比較不可)
    - 確認: uncertain_count >= 3

#### グループ4: CSV値が null（2 件）

13. **test_csv_value_null_single_item**
    - CSV値が null の項目が 1 つ
    - 期待: unreadable_items に追加
    - 確認: unreadable_count = 1

14. **test_csv_value_null_multiple_items**
    - CSV値が null の項目が複数
    - 期待: phase3_status = 'review'

#### グループ5: 複数CSV候補（2 件）

15. **test_multiple_csv_candidates_clear_winner**
    - 候補が複数で、最高スコアが明確
    - 期待: best_match を選出、phase3_status 決定
    - 確認: score_diff > 100

16. **test_multiple_csv_candidates_close_score**
    - 複数候補のスコアが接近
    - 期待: phase3_status = 'review'
    - 確認: score_diff < 50

#### グループ6: マッピング条件（3 件）

17. **test_exclude_mapping_status_uncertain**
    - mapping_status = 'uncertain' の項目は除外
    - 期待: 比較対象外
    - 確認: field_comparisons から除外

18. **test_exclude_needs_confirmation_true**
    - needs_confirmation = true の項目は除外
    - 期待: 比較対象外
    - 確認: field_comparisons から除外

19. **test_exclude_empty_csv_column_code**
    - csv_column_code が空欄の項目は除外
    - 期待: 比較対象外

#### グループ7: 5G→10G 合算対応（1 件）

20. **test_courseup_not_combined**
    - 5G と 10G は分別したまま比較
    - 期待: 別項目として扱う
    - 確認: memo に「要確認」の場合は参考情報のみ

### 8.2 テストデータの構造

```python
# ダミー confirmed_mapping
confirmed_mapping = pd.DataFrame({
    'fax_item_name': ['ネット追加(HH)', '地デジBS', ...],
    'csv_column_code': ['HH', 'GT', ...],
    'csv_column_number': [216, 201, ...],
    'mapping_status': ['confirmed', 'confirmed', ...],
    'needs_confirmation': [False, False, ...],
})

# ダミー pdf_record
pdf_record = {
    'page_no': 1,
    'store_name': 'ａｕショップ　ニトリモール枚方',
    'staff_name': None,
    'tablet_no': None,
    'data_no': None,
    'mapped_values': {
        'HH': 0,
        'GT': 1,
        'GS': 'uncertain',
        ...
    }
}

# ダミー csv_row
csv_row = pd.Series({
    0: '2026/06/05',      # A列（日付）
    215: 0,               # HH列（csv_column_number=216, 1-indexed）
    200: 1,               # GT列（csv_column_number=201, 1-indexed）
    ...
})
```

---

## 9. 変更対象ファイル候補

### 9.1 必須変更（Phase 3）

| ファイル | 変更内容 | 説明 |
|---------|---------|------|
| **reconciliation_phase1.py** | `_compare_fields()` 新規 | PDF値とCSV値を比較 |
| | `_calculate_field_comparison_score()` 新規 | 比較スコアを計算 |
| | `_determine_phase3_status()` 新規 | Phase 3 判定ルール |
| | `reconcile_pdf_with_csv()` 拡張 | Step 5 で Phase 3 処理を追加 |
| | `_create_review_result()` 拡張 | Phase 3 出力項目を追加 |
| **tests/test_phase3_field_comparison.py** | 新規作成 | 比較判定のテストスイート |

### 9.2 参照のみ（変更なし）

| ファイル | 参照方法 |
|---------|--------|
| **pdf_csv_field_mapping.csv** | self.confirmed_mapping として既読み込み |
| **reconciliation_phase1.py** (Phase 1, 2) | 既存メソッド活用 |

### 9.3 後続フェーズで検討

| ファイル | 検討事項 | 時期 |
|---------|--------|------|
| **app.py** | Phase 3 結果の UI 表示（複数候補表示など） | Phase 4+ |
| **reconciliation.py** | Phase 1-3 結果の統合・フロー管理 | 将来 |

---

## 10. 実装時の注意点

### 10.1 スコア計算の安定性

**懸念**: 項目数によってスコア絶対値が変動

```python
# 例：20項目比較と 50項目比較では基本スコアが異なる
# 20項目全一致: 20 * 10 = 200
# 50項目全一致: 50 * 10 = 500
# → 閾値を相対値で設定する必要がある
```

**対応**:
```python
# 相対値での判定
match_rate = matched_count / total_count  # 0-1
if match_rate >= 0.95:  # 95% 以上一致
    phase3_status = 'match'
elif match_rate <= 0.80:  # 80% 以下
    phase3_status = 'mismatch'
else:  # 80-95%
    phase3_status = 'review'
```

### 10.2 CSV値のデータ型統一

**懸念**: CSV値が文字列「1」か数値 1 かで比較結果が異なる

```python
# PDF側: int / float
# CSV側: str / int / None / nan

def normalize_csv_value(val):
    if val is None or pd.isna(val):
        return None
    try:
        return int(float(str(val).replace(',', '')))
    except:
        return None
```

### 10.3 CSV列インデックスの正確性

**懸念**: csv_column_number (1-indexed) を 0-indexed に変換時のズレ

```python
# 正: csv_row.iloc[csv_column_number - 1]
# 誤: csv_row.iloc[csv_column_number]

# 列 216 の場合
# 正: csv_row.iloc[215]
```

### 10.4 不確定項目の扱い

**懸念**: uncertain / null が「比較対象外」か「比較対象」か曖昧

```python
# ポリシー: 「比較対象外」だが結果には明示
# - unreadable_count に含める
# - field_comparisons に記録
# - review_reasons に理由を記載
```

### 10.5 複数CSV候補での最適候補選出

**懸念**: スコアだけで最適候補を決めると、外れる可能性がある

```python
# Phase 3 では「スコア最高」の行を best_match に
# ただし複数候補のスコアが接近していれば phase3_status = 'review'
# → 人間判定を必須にする

if len(candidates_with_scores) > 1 and score_diff < 50:
    return 'review'
```

### 10.6 Phase 2, 3 の判定の統合

**懸念**: Phase 2 では「候補見つかった」ですが、Phase 3 では「不一致」の場合の扱い

```
Phase 2: match_status = 'candidate_found'  (1件見つかった)
Phase 3: phase3_status = 'mismatch'        (不一致)

→ 最終 status = 'mismatch' に統一
→ ただし review_reasons に Phase 2, 3 双方の理由を記載
```

---

## 11. 出力形式の詳細

### 11.1 field_comparisons の例

```python
[
    # ケース1: 完全一致
    {
        'fax_item_name': 'ネット追加(HH)',
        'csv_column_code': 'HH',
        'csv_column_number': 216,
        'pdf_value': 0,
        'csv_value': 0,
        'pdf_value_status': 'confirmed',
        'csv_value_status': 'confirmed',
        'comparison_status': 'match',
        'match_type': 'exact',
        'reason': 'Both values are 0',
        'comparison_score': 10,
    },
    
    # ケース2: 不一致
    {
        'fax_item_name': '地デジBS',
        'csv_column_code': 'GT',
        'csv_column_number': 201,
        'pdf_value': 1,
        'csv_value': 2,
        'pdf_value_status': 'confirmed',
        'csv_value_status': 'confirmed',
        'comparison_status': 'diff',
        'match_type': 'mismatch',
        'reason': 'PDF=1, CSV=2',
        'comparison_score': -5,
    },
    
    # ケース3: PDF値が不確定
    {
        'fax_item_name': 'CS',
        'csv_column_code': 'GU',
        'csv_column_number': 199,
        'pdf_value': 'uncertain',
        'csv_value': 1,
        'pdf_value_status': 'uncertain',
        'csv_value_status': 'confirmed',
        'comparison_status': 'uncertain',
        'match_type': 'cannot_compare',
        'reason': 'PDF value is uncertain (tally mark途中形)',
        'comparison_score': 0,
    },
    
    # ケース4: CSV値が null
    {
        'fax_item_name': 'eo光電話(GS)',
        'csv_column_code': 'GS',
        'csv_column_number': 201,
        'pdf_value': 1,
        'csv_value': None,
        'pdf_value_status': 'confirmed',
        'csv_value_status': 'null',
        'comparison_status': 'unreadable',
        'match_type': 'cannot_compare',
        'reason': 'CSV value is null',
        'comparison_score': 0,
    },
]
```

### 11.2 field_comparison_summary の例

```python
{
    'total_items': 42,
    'matched_items': 38,
    'diff_items': 2,
    'uncertain_items': 1,
    'unreadable_items': 1,
    
    'comparison_base_score': 370,           # 38*10 + 2*(-5)
    'comparison_match_rate': 0.905,         # 38/42
    'phase3_status': 'match',
    'phase3_score': 620,                    # 370 + 200 + 50
}
```

---

## 12. 実装の段階

### Stage 1: 基本機能

```
_compare_fields() の実装
├─ 確定済み項目の抽出
├─ PDF値とCSV値の比較
└─ field_comparisons の構築
```

### Stage 2: スコア計算

```
_calculate_field_comparison_score() の実装
├─ 項目ごとのスコア計算
├─ 合計スコア算出
└─ match_rate の計算
```

### Stage 3: 判定ロジック

```
_determine_phase3_status() の実装
├─ 条件判定（match / mismatch / review）
├─ 複数候補での候補選出
└─ ボーナススコア統合
```

### Stage 4: 統合

```
reconcile_pdf_with_csv() 拡張
├─ Phase 3 処理の追加
├─ 出力項目の追加
└─ Phase 1-3 結果の統合
```

### Stage 5: テスト

```
test_phase3_field_comparison.py の実装
└─ 16～20 テストケース
```

---

## 13. リスク & 対応

| リスク | 影響 | 対応 |
|--------|------|------|
| スコア絶対値の不安定性 | 閾値決定が困難 | 相対値 (match_rate) での判定を優先 |
| CSV値のデータ型ゆれ | 比較失敗 | normalize_csv_value() で統一化 |
| 複数候補のスコア接近 | 最適候補選出失敗 | スコア差が小さい場合は review に |
| PDF値が uncertain 多発 | 比較不可能 | review_reasons に理由を明示 |
| Phase 2-3 判定の矛盾 | ユーザー混乱 | 最終 status は Phase 3 優先、ただし warnings に記載 |

---

## 14. マイルストーン

| 対象 | 進捗 |
|------|------|
| **Phase 1** | ✅ 完了（shop_code 変換） |
| **Phase 2** | ✅ 完了（日付+店舗コード検索） |
| **Phase 3** | 📋 計画中（集計値比較） |
| **Phase 4** | ⏳ 検討中（UI/最終判定） |

---

## 15. 期待される成果

### デリバラブル

- `reconciliation_phase1.py` 拡張版
  - `_compare_fields()` メソッド追加
  - `_calculate_field_comparison_score()` メソッド追加
  - `_determine_phase3_status()` メソッド追加
  - `reconcile_pdf_with_csv()` 拡張

- `tests/test_phase3_field_comparison.py` 新規作成
  - 16～20 テストケース
  - 全テスト PASSED

### 品質指標

- テスト成功率: 100%
- コードカバレッジ: >= 90%
- ドキュメント完成度: 100%

---

**計画書作成日**: 2026-06-05  
**版**: 1.0 (設計段階)  
**ステータス**: 実装前レビュー待ち


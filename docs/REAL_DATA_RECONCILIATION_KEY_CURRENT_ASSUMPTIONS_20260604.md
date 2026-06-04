# リアルデータ照合キー分析レポート（現時点の前提）
## 店舗・スタッフマスタ × Salesforce CSV × FAX帳票PDF

**作成日**: 2026-06-04（片山様確認前の現時点の前提）  
**対象ファイル**: report1780043296399.csv / 20260529130020168.pdf  
**照合方針**: CSV 1行 = PDF 1枚、日付 + 店舗コード + 数値一致度（補助: 店舗名・担当者名）

---

## 📊 アプリ・分析現状

### ✅ アプリ動作状態

| 機能 | 状態 | 備考 |
|------|------|------|
| CSV読込 | ✓ | 43行 × 283列、cp932対応 |
| 日付フィルタ | ✓ | 2026/05/17 → 25件抽出 |
| PDFアップロード | ✓ | 複数対応 |
| PDF str エラー | ✓ | 防御処理実装済み |
| download_button | ✓ | key追加で修正済み |
| 照合結果表示 | ✓ | 1件生成（要確認1件） |
| 本格ロジック | ✗ | 前提整理段階 |

### 🎯 分析ステータス

- ✓ CSV構造確認完了（店舗コード列281確認）
- ✓ マスタデータ確認完了
- ✓ 本命キー確定（日付 + 店舗コード + 数値一致度）
- ✓ 補助情報の位置づけ確定
- △ 片山様確認待ち（7項目）

---

## 1. CSV側の確認結果（最終版）

### 1.1 確認できた列

| 列No | 列名 | 内容 | 用途 |
|------|------|------|------|
| 281 | 法人・店舗(取扱コード) | AU1K... | 照合キー |
| 283 | 日付 | YYYY/MM/DD | 照合キー |

### 1.2 確認できなかった列（CSV側では）

| 項目 | 状態 | 用途 |
|------|------|------|
| スタッフ名 / スタッフNO | **見つかりませんでした** | PDF側補助情報として扱う |
| タブレットNo | **見つかりませんでした** | PDF側補助情報として扱う |
| 日報DataNo | **見つかりませんでした** | 使用しない |

**重要**: これらの情報はPDF側からは取得し、補助情報として扱うが、CSV直接照合キーには使わない。

---

## 2. 本命照合キー（確定）

### 主判定: 日付 + 店舗コード + マッピング済み数値項目の一致度

```
ステップ1: 対象営業日でCSVを絞る
           ↓
ステップ2: PDF 1ページから店舗情報・数値を抽出
           ↓
ステップ3: 店舗コード（CSV列281）で候補行を絞る
           ↓
ステップ4: マッピング済み数値項目の一致度で判定
           ↓
ステップ5: 補助情報で信頼度を上げる or 要確認に分類
```

### 補助判定: PDF上の店舗名・担当者名

**使い方**:
1. PDF上の店舗名を読む → 店舗マスタと照合 → 店舗コード候補を出す
2. PDF上の担当者名を読む → スタッフマスタと照合 → 存在確認（加点）
3. 但しCSV側にスタッフ列がないため、スタッフ名だけでは確定しない
4. 最終判定は数値一致度で行う

### 使わないもの

| 項目 | 理由 |
|------|------|
| 日報No | あてにならない |
| CSV側タブレットNo | CSV側に列がない |
| CSV側スタッフ列 | CSV側に確認できていない |

---

## 3. 照合キー候補の最新評価

### 候補A: 日付 + 店舗コード

| 項目 | 評価 |
|------|------|
| 実用可能性 | ◎ 基本キー |
| 注記 | 同一店舗複数行は数値一致度で区別 |

### 候補E: 日付 + 店舗コード + マッピング済み数値一致度

| 項目 | 評価 |
|------|------|
| 実用可能性 | **◎◎ 本命** |
| 優位性 | CSV側必要列すべて存在、PDF側で取得可能 |

### 候補B～D, F: 補助情報扱い

| 候補 | 用途 |
|------|------|
| B: 日付 + 店舗NO | 店舗マスタ変換用 |
| C: 日付 + 店舗名 | 店舗マスタマッチング用 |
| D: 日付 + 店舗 + タブレット | PDF店舗推定補助 |
| F: 日報No | 使用しない（参考のみ） |

---

## 4. 最小照合ロジック（9ステップ・現在の理解）

### ステップ1: CSVを対象営業日で絞る

```python
df_target = df_csv[df_csv['日付'] == target_date]
# 結果: 対象営業日のCSVレコード抽出（例: 25件）
```

### ステップ2～3: PDFを1ページ = 1帳票として扱う

```python
for page_no in range(1, total_pages + 1):
    page_data = extract_page_as_record(pdf, page_no)
    # PDF 1ページを独立した帳票として処理
```

### ステップ4: PDFから以下を抽出する

**主要項目（照合用）**:
- マッピング確定済みの数値項目
  - 案件欄（au案件新規、DL、AV、DM など）
  - 内訳欄（5G紹介、10G紹介、eo光、フレッツ光など）
  - スタッフ活動（ポイント合計など）
  - 新規オプション（eo光電話、光テレビなど）
  - 既存対応（ネット追加、eTVサービスなど）

**補助項目（情報抽出）**:
- 店舗名（店舗推定用）
- 担当者名（信頼度上昇用）
- タブレットNo（店舗推定補助）

**参考項目**:
- 日報No（参考のみ）

**除外**:
- item 28（コースアップ→5G→10G）未使用
- 名称確認待ち項目
- コード未確定項目

### ステップ5: 店舗情報を正規化して店舗コード候補を出す

```python
# PDF店舗名 → 店舗マスタと照合 → store_code 候補
pdf_store_code = match_with_store_master(pdf_page_data['store_name'])

# PDF担当者名 → スタッフマスタと照合 → 存在確認（補助情報）
staff_found = check_staff_master(pdf_page_data['staff_name'])
# ただし CSV側に対応列がないため、確定キーにはしない
```

### ステップ6: CSV候補行を絞る

```python
candidates = df_target[df_target.iloc[:, 280] == pdf_store_code]
# CSV列281（法人・店舗(取扱コード)）で候補を抽出
```

**結果**:
- 候補1行 → ステップ7へ
- 候補複数 → ステップ8へ
- 候補なし → 「要確認」へ

### ステップ7: 候補が1行の場合、マッピング済み数値を照合

```python
def reconcile_single_match(csv_record, pdf_data):
    """
    マッピング表に基づいて数値比較
    """
    match_count = 0
    diff_count = 0
    
    for mapped_item in mapping_table:
        if mapped_item['mapping_status'] != 'confirmed':
            continue  # 確定済みのみ対象
        
        csv_value = csv_record.get(mapped_item['csv_column'])
        pdf_value = pdf_data.get(mapped_item['pdf_field'])
        
        if csv_value == pdf_value:
            match_count += 1
        else:
            diff_count += 1
    
    return match_count, diff_count
```

### ステップ8: 候補が複数の場合、数値一致度で比較

```python
def find_best_match(candidates, pdf_data):
    """
    複数候補から一致度が高い行を選択
    """
    best_match = None
    max_match_count = -1
    
    for _, csv_record in candidates.iterrows():
        match_count, diff_count = reconcile_single_match(csv_record, pdf_data)
        
        if match_count > max_match_count:
            max_match_count = match_count
            best_match = csv_record
    
    # 複数行が同じ一致度の場合は要確認
    return best_match
```

**判定基準**:
- 全項目一致 → その行を選択
- 主要項目一致 → その行を選択
- 複数行が同等 → 「要確認」（同一店舗・同一日付で複数行の可能性）

### ステップ9: スコア計算と最終判定

```python
def calculate_confidence_score(csv_record, pdf_data):
    """
    補助情報も含めて信頼度スコアを計算
    """
    score = 0
    
    # 主判定（必須）
    if pdf_data['date'] == csv_record['日付']:
        score += 100  # 日付一致
    
    if pdf_data['store_code'] == csv_record['store_code']:
        score += 200  # 店舗コード一致
    
    # 数値一致（重要）
    match_count, diff_count = reconcile_single_match(csv_record, pdf_data)
    score += match_count * 10  # マッピング済み項目 1件 10点
    score -= diff_count * 5    # 差分 1件 -5点
    
    # 補助情報（参考）
    if pdf_data.get('store_name_matched'):
        score += 5  # 店舗名一致
    
    if pdf_data.get('staff_found_in_master'):
        score += 2  # スタッフ名が存在
    
    return score
```

### 最終ステータス分類

**一致**:
- 日付一致
- 店舗コード一致
- マッピング済み主要項目の一致度が高い（許容値内）
- 補助情報に大きな矛盾がない

**不一致**:
- 日付一致、店舗コード一致
- マッピング済み項目に差分がある

**要確認**:
- 店舗候補が見つからない
- 店舗候補が複数（数値一致度で決めきれない）
- PDF店舗名が読めない
- PDF数値が読めない
- 同一店舗・同一日付でCSVが複数行（再送・修正後データの可能性）
- スタッフ名はスタッフマスタに存在するがCSV側に対応列がない

---

## 5. 同一店舗・同一日付で複数CSV行がある場合の扱い

### 最新方針（確定）

**原則**: 合算しない、複数行を提示して判定

**処理フロー**:
1. PDF 1ページに対応するCSV候補が複数出た
2. 各候補行について数値一致度を計算
3. 最も一致度が高い行を候補にする
4. 決めきれない場合は「要確認」に分類
5. 人間確認で判断（再送・修正後データ・重複登録など）

**理由**:
- CSV複数行の理由が不明（確認待ち）
- データ品質：再送・修正後・重複の可能性
- 初期版では安全側に倒す

---

## 6. PDF上の店舗名・担当者名の扱い（確定）

### 重要な位置づけ

```
PDF上の店舗名・担当者名は、照合候補の信頼度を上げる補助情報として扱う。

特に担当者名は、CSV側に対応列が確認できていないため、
確定キーではなく、確認補助・画面表示・候補順位付けに利用する。
```

### 使用フロー

```
PDF上の情報を読む
  ↓
店舗マスタ / スタッフマスタと照合
  ↓
信頼度スコアに反映
  ↓
ただし、CSV直接キーにはしない
  ↓
最終判定は数値一致度で行う
```

### 具体例

**例1**: 店舗名一致、スタッフ名も一致、数値も一致 → 「一致」

**例2**: 店舗名一致、スタッフ名は読めたがCSV側に列がない、数値一致 → 「一致」（スタッフ名は参考）

**例3**: 店舗名一致、スタッフ名存在確認、数値差分あり → 「不一致」

**例4**: 店舗名読めない、複数店舗候補 → 「要確認」

---

## 7. 片山様に確認すべき事項（現時点で確認待ち）

### 【必須】

1. **CSV 1行 = PDF 1枚対応で進めてよいか**

2. **CSV側の「法人・店舗(取扱コード)」について**
   - 店舗マスタの代理店コードと同一概念でよいか

3. **同一店舗・同一日付で複数CSV行がある場合**
   - 理由（再送・修正後・重複など）
   - 複数行を提示して人間確認でよいか

4. **マッピング確定済みの項目を照合対象にしてよいか**
   - 優先順位はマッピング確定済みから進める方針でよいか
   - 未使用・名称確認待ち・コード未確定項目は初期版で除外してよいか

5. **PDF上の店舗名・担当者名を補助情報として使ってよいか**
   - CSV側に対応列がないため、確定キーにはしない方針でよいか

6. **日報No、タブレットNoについて**
   - 日報Noは使わない方針でよいか
   - タブレットNoはPDF店舗推定補助のみでよいか

7. **初期版の範囲確認**
   - Phase 1 は「日付 + 店舗コード + 数値一致度」で進める方針でよいか

---

## 8. マッピング済み項目の優先順位（確定版）

### 優先1: 確定済みで実装すべき項目

- 案件欄（au案件新規/既存 × 紹介/声掛）
- 内訳欄（5G, 10G, eo光, フレッツ光など × 紹介/声掛）
- 既存対応欄（ネット追加, eTVサービスなど）
- スタッフ活動欄（ポイント合計など）
- 新規オプション欄（eo光電話など）
- 合計欄

### 優先2: 段階的に実装

- PDF側で読取精度が高い数値項目
- 手書き欄で信頼度が高い項目

### 除外（初期版）

- 日報No（使わない）
- item 28（コースアップ→5G→10G、未使用）
- 名称確認待ち項目
- コード未確定項目
- 正式運用確認待ち項目

---

## 9. 現時点での制約確認

- ✓ 日報Noを照合キーにしていない
- ✓ CSV側タブレットNoを使わない
- ✓ CSV側スタッフ列を前提にしない
- ✓ CSV複数行を合算しない
- ✓ PDF複数ページを合算しない
- ✓ 5G→10G を IG + IH として扱わない
- ✓ sum(IG, IH) を書かない
- ✓ item 28 を照合対象にしない
- ✓ reconciliation.py に本格ロジック入れない
- ✓ app.py に本格照合ロジック入れない

---

## 10. コミット方針（現時点の設計メモとして）

### A. 不具合修正系（すぐコミット可能）

**ファイル**:
- app.py（防御処理 + key追加）
- extractor.py（型チェック）

**メッセージ**:
```
fix: stabilize PDF extraction handling and download buttons
```

**内容**:
- PDF読み取り str型チェック
- isinstance 防御処理
- download_button key追加

**ステータス**: 再テスト完了後すぐにコミット可能

### B. 分析系（現時点の前提記録）

**ファイル**:
- docs/REAL_DATA_RECONCILIATION_KEY_FINAL_CONFIRMED_20260604.md（新規）
- docs/RECONCILIATION_KEY_FINAL_REVISION_SUMMARY_20260604.md（参考）
- data/test_outputs/csv_store_master_match_20260604.csv
- scripts/analyze_reconciliation_keys.py

**メッセージ**:
```
docs: document real data reconciliation key assumptions

Current state:
- CSV side: no tablet_no, staff columns confirmed
- PDF side: store name, staff name available as auxiliary info
- Primary key: date + store_code + mapped item matching
- Secondary: PDF store/staff names for confidence scoring
- Phase 1 scope: confirmed mapping items only

Pending:
- Confirmation from Katayama-san on 7 items
```

**ステータス**: 片山様確認待ちであっても、現時点の設計メモとしてコミット可能

---

## 11. 次のステップ

1. 片山様への確認依頼（確認事項7点）
2. CSV詳細列検索（スタッフ列など再確認）
3. PDF OCR試行（数値抽出精度確認）
4. 回答受領後、Phase 1 ロジック実装

---

**最終確認日**: 2026-06-04  
**ステータス**: 前提確定 → 片山様確認待ち → Phase 1 実装へ


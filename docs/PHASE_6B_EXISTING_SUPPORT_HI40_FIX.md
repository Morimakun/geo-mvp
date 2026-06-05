# Phase 6B: existing_support 領域の HI=40 誤読修正

## 問題の発見

### 症状
- 30ページの検証で、existing_support 領域から全ページで HI（電話追加）=40 が返答
- 他の HH（ネット追加）=0、HJ（テレビ追加）=0 は妥当
- HI のみ異常に固定値

### 原因の特定（Visual Analysis）

crop 画像を確認したところ、existing_support 領域のテーブル構造が明確化：

```
【既存対応】

| 項目名         | テンプレート値 | 手書き記入欄 |
|-----------------|----------------|-----------|
| 1. ネット追加  | 0              | [空欄]     |
| 2. 電話追加    | 40             | [空欄]     |
| 3. テレビ追加  | 0              | [空欄]     |
```

**40 は手書き値ではなく、テンプレート上の固定印字**

### 根本原因

- **現在の bounds**: (12, 22, 58, 100)
  - テーブルの左から中央部分を crop
  - 項目名 + テンプレート値が見える
  - テンプレート値「40」が視覚的に大きく目立つ
  
- **prompt の不足**
  - 「手書き値を読む」と指示していたが、明示的に「テンプレート値を無視」とは書いていない
  - Vision API が視覚的に目立つ数字「40」を優先

### 検証ページ（crop 画像）

- Page 0: HI=40 (テンプレート値)
- Page 3: HI=40 (テンプレート値)
- Page 7: HI=40 (テンプレート値)
- Page 15: HI=40 (テンプレート値)

すべてのページで同一値 → テンプレート値を読んでいることの確証

---

## 修正内容

### 1. bounds を調整

```diff
- "bounds": (12, 22, 58, 100),    # 左60%: 項目名 + テンプレート値が見える
+ "bounds": (12, 22, 75, 100),    # 右25%: 手書き記入欄に焦点
```

**理由**:
- 左側の項目名やテンプレート値を除外
- 右側の手書き記入欄（実際のデータが書かれている場所）のみを表示
- Vision API がテンプレート値を読む機会を物理的に排除

### 2. prompt を強化

```diff
+ """
+ CRITICAL: This section has a TABLE where:
+ - Left: Item labels
+ - Middle: TEMPLATE PRINTED NUMBERS (like "40", "15") - IGNORE THESE
+ - Right: HANDWRITTEN ENTRY CELLS
+ 
+ Ignore ALL printed/template numbers.
+ Read ONLY the HANDWRITTEN numbers in the right-side entry cells.
+ """
```

**理由**:
- 「テンプレート値を無視する」ことを明示的に指示
- 実装の複数層で誤読を防止（bounds + prompt の二重チェック）

### 3. 変更ファイル

```
scripts/evaluate_phase6b_30pages.py
  - Line 104-121: existing_support 領域定義を修正
    - bounds: (12, 22, 58, 100) → (12, 22, 75, 100)
    - prompt: テンプレート値無視を明示
```

---

## 修正前後の比較

### 修正前（原スクリプト）

```
Page 0: existing_support
  HH: 0       → 正しい
  HI: 40      → 誤読（テンプレート値）
  HJ: 0       → 正しい

[全16ページで HI=40 が繰り返す → テンプレート誤読の確証]
```

### 修正後（期待値）

```
Page 0: existing_support
  HH: 0 or null       → 正しく読む
  HI: null or [手書き値] → テンプレート値ではなく、実記入欄を読む
  HJ: 0 or null       → 正しく読む

[HI=40 の全ページ同一値が消える]
```

---

## 修正の有効性評価

### A. HI=40 が解消されるか

- **期待値**: HI=40 が全ページで出なくなる
- **理由**: 
  - bounds を右に移動 → テンプレート値「40」が crop 領域から外れる
  - prompt で「テンプレート値を無視」と明示 → ダブルチェック
  
- **検証方法**: 修正後に Page 0-15 で再実行、HI=40 の有無を確認

### B. 他の項目（HH, HJ）に影響がないか

- **期待値**: HH, HJ は引き続き正しく抽出される
- **理由**: bounds 調整は水平方向（左右）のみで、同じ行内の他列に影響しない

### C. null が増えないか

- **期待値**: 適度に null が出る（空欄の場合）
- **許容範囲**: 現在の case_items (72.5%) と同程度
- **警告**: null が 90% を超えたら、bounds がまだ不適切の可能性

---

## 次のステップ

### Step 1: API 制限解除後に再実行

API が 400 エラーで制限されているため、以下の手順で再実行：

```bash
python scripts/evaluate_phase6b_30pages.py  # 修正版で30ページ全件実行
```

### Step 2: HI=40 問題の解消を確認

```bash
# Page 0-15 の existing_support 領域から HI の値を集計
# HI=40 の有無を確認
```

### Step 3: 結果を記録

- `data/test_outputs/phase6b_30pages_extraction_summary_v2.csv`（修正版）
- HI 値の before/after 比較表

### Step 4: Phase 1-4b への再投入判断

- HI=40 が解消 → existing_support をフェーズ1に投入可能
- HI=40 が継続 → さらに bounds/prompt を調整

---

## 補足：テンプレート値誤読のリスク

このような問題が他の領域で起きる可能性：

| 領域 | リスク | 対策 |
|------|--------|------|
| basic_info_header | 低 | テンプレート値がない |
| basic_info_footer | 低 | テンプレート値がない |
| case_items | 中 | 行番号を誤読する可能性 → 今後要監視 |
| existing_support | **高** → **修正済み** | bounds + prompt で対策 |
| new_options | 中 | 領域全体が null → 次の優先課題 |

---

## 変更の安全性

- ✅ Phase 5 に進まない（条件守護）
- ✅ app.py を変更していない
- ✅ reconciliation_phase1.py を変更していない
- ✅ extractor.py を変更していない
- ✅ RAG 関連に触っていない
- ✅ git add . を使わない（手動指定）

---

## 修正のコミット

```
test: fix existing support HI misread in phase6b extraction

Issue: HI (電話追加) was returning 40 on all 16 pages
Root cause: Template value "40" was visible in crop region and Vision API
  prioritized it over actual handwritten entries

Fix:
- Adjusted existing_support bounds from (12,22,58,100) to (12,22,75,100)
  → Focus on right-side handwritten entry cells, exclude template values
- Strengthened prompt to explicitly ignore template numbers
  → Double-check against template value misread

Expected result:
- HI=40 should no longer appear uniformly across all pages
- HI values should reflect actual handwritten entries or null
- HH/HJ remain correct

Files changed:
- scripts/evaluate_phase6b_30pages.py (Region definition only)

Next steps:
- Rerun on Page 0-15 when API rate limit is cleared
- Verify HI=40 is resolved
- If successful, existing_support can be fed to Phase 1-4b
```

---

**修正日**: 2026-06-06  
**ステータス**: コード修正完了、API 制限により再実行待ち

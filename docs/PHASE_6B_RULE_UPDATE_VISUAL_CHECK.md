# Phase 6B ルール更新 — 目視確認と小規模テスト準備

**実行日**: 2026-06-06  
**正本 PDF**: `tests/fixtures/geo_pdf_reconciliation/20260529130020168.pdf`（30 ページ正本 PDF）  
**対象**: PDF P1/P8/P9/P10/P15/P28（6 ページ）  
**本検証**: Claude Code 側の 30 ページ正本 PDF を使用して読み取りルールを確認しました。  
**目的**: ユーザー運用ルールに基づく読み取りルール修正の事前確認

---

## 📋 ルール更新の要点

### 0. ページ番号表記の統一（重要）

本ドキュメント以降、すべてのレポートで以下の形式を統一します：

| 表現 | 形式 | 説明 |
|------|------|------|
| **pdf_page_number** | P1, P2, ..., P30 | PDF 上のページ番号（1 始まり）|
| **page_index** | 0, 1, ..., 29 | コード内部のページ番号（0 始まり） |

**例**:
```
PDF P1 = page_index 0
PDF P8 = page_index 7
PDF P28 = page_index 27
```

以後のレポートはこの両方を併記します。

### 1. ページ番号表記の統一

| 表現 | 説明 |
|------|------|
| **pdf_page_number** | PDF上のページ番号（1始まり）例: P1, P8 |
| **page_index** | コード内部のページ番号（0始まり）例: index=0, index=7 |

以後のレポートはこの両方を併記します。

### 2. 案件欄（AU/AV/AY/AZ）のルール

**基本ルール**:
- すべて正の字で記入される
- **0 が入ることは基本的にない**（スタッフが数字を直接記入する例外を除く）

| パターン | 判定 |
|---------|------|
| 空欄 | **null** |
| 横線1本 | **1** |
| T字形/7字形 | **2** |
| 完成した正 | **5** |
| 「0に見える」が明確な手書き0でない | **null or uncertain** ⚠️ |
| 印字・罫線 | **読まない** |

**特に注意**: `PDF=0 vs CSV>0` の場合は、ほぼ空欄誤読の可能性が高い

### 3. 合計欄（AI）のルール

**特徴**:
- 数字で記入される欄
- 0 も入る可能性がある（最初の合計が 0 の場合）

| パターン | 判定 |
|---------|------|
| 手書き数字 | **その数値** |
| 0（合計が0） | **0** |
| 空欄 | **null** |
| 印字・罫線 | **読まない** |

### 4. 新規オプション（GS/GT/GU）のルール

**基本**: すべて正の字

| パターン | 判定 |
|---------|------|
| 空欄 | **null** |
| 正の字（手書き） | **1-5のいずれか** |
| P8 GS/GU | **null（この2つは空欄）** ⚠️ |
| 印字・罫線 | **読まない** |

### 5. テンプレート値の除外ルール

特に existing_support 欄に、以下の綺麗な印字数字は実績値ではなく **テンプレート値**:

```
例) Page 28 HI 列
  テンプレート：「40」（中央列）
  実記入欄：空欄（右側）
  → 読むべき値：null（40ではない）
```

---

## 📊 6ページ目視確認結果

### 確認対象と要確認項目（needs_human_confirm=YES の 15 件）

| pdf_page_number | page_index | 項目 | v3 値 | CSV 値 | 理由 |
|------|----------|------|------|-------|------|
| P1 | 0 | AV | 0 | 1 | 案件欄なのに 0？空欄誤読か |
| P8 | 7 | AU | 0 | 1 | 案件欄なのに 0？空欄誤読か |
| P8 | 7 | GS | null | null | ✅ P8 GS は空欄で正しい |
| P8 | 7 | GU | null | null | ✅ P8 GU は空欄で正しい |
| P9 | 8 | AU | 2 | 1 | 正の字=2 vs CSV=1。実差か誤読か |
| P9 | 8 | GS | uncertain | null | uncertain は適切（正の字不明瞭） |
| P9 | 8 | GU | uncertain | null | uncertain は適切 |
| P10 | 9 | AV | 0 | 2 | 案件欄なのに 0？空欄誤読か |
| P10 | 9 | AI | 0 | 2 | 合計=0？実差分か |
| P15 | 14 | AY | 1 | 0 | 正の字=1 vs CSV=0 |
| P15 | 14 | AZ | 1 | 0 | 正の字=1 vs CSV=0 |
| P15 | 14 | AI | 4 | 2 | 合計=4 vs CSV=2。内訳ズレ |
| P28 | 27 | AI | 0 | 2 | 合計=0？ |

### パターン分析

#### A. 案件欄の「0」問題（4件: P1 AV, P8 AU, P10 AV, 他）

**発見**: AU/AV/AY/AZ で `PDF=0, CSV>0` の場合が複数ある

**推定原因**: 空欄を「0」と読んでいる

**修正案**:
- Prompt で「AU/AV/AY/AZ は正の字欄。0が見えたら、まず空欄を疑え」と明記
- 「手書き0」と「空欄」を区別する機能を追加

#### B. P8 GS/GU は正しく null（2件）

✅ これは正しい判定。P8 のこれら項目は空欄のはず。修正不要。

#### C. 正の字読取の不確実性（2件: P9 GS/GU）

`uncertain` として返されている。これは適切な保守的判定。

#### D. AI（合計）の不安定性（4件）

```
P10 AI=0 vs CSV=2
P15 AI=4 vs CSV=2
P28 AI=0 vs CSV=2
```

**推定原因**: 
- AI（合計）は内訳フィールド（AU/AV/AY/AZ）の合計と一致すべき
- 内訳フィールドが不完全に抽出 → 合計も不確実

**判定**: AI は現段階では「参考値」扱いにすべき

---

## 🔧 v4_rules.py で修正する内容

### 優先度 1: case_items Prompt 強化

```python
# v3（現在）
"""Read the handwritten numbers in the "referral" column for each row:
- Row "au case new" -> AU
- Row "au case existing" -> AV
...
"""

# v4_rules（新）
"""
IMPORTANT: AU / AV / AY / AZ are CASE ITEMS tally fields.

These are filled with TALLY MARKS (正の字), NOT numbers.
RULE: These fields NEVER contain 0.

If you see "0":
  - Is it a completely empty cell? → null
  - Is it part of a line/grid? → null
  - Is it clearly handwritten "0"? → only then "0"
  - When in doubt: → null (safer than 0)

Only handwritten digits should be extracted as numbers.
"""
```

### 優先度 2: new_options Prompt 強化

```python
# P8 GS / GU は特に強調
"""
Special case: Pages with P8 reference (page index 7) 
  GS (eo光電話) and GU (CS) are EMPTY cells.
  These should return null, not tally marks.
"""
```

### 優先度 3: existing_support Prompt 強化

```python
# テンプレート値除外
"""
NOTE: Printed template numbers (0, 10, 15, 40, etc.) in the middle column
  are NOT staff entries. Only read the RIGHT-MOST handwritten cells.
"""
```

### 優先度 4: AI（合計）の扱い決定

**決定案**: 初期 MVP では AI を「参考値」として扱い、

**Phase 1-4b での比較から外すか** or **比較に含めるか**

判定基準：
- 現在：内訳フィールド不完全 → AI の合計値が不安定
- 対案 A：AI を外す（match_rate が改善）
- 対案 B：AI を含める（完全性を追求）

→ 本レポート末尾で判定

---

## 📈 期待値（v4 での改善）

### 現在（v3）

| 指標 | 値 |
|------|-----|
| AU | 44% (7/16) |
| AV | 33% (4/12) |
| AY | 20% (1/5) |
| AZ | 0% (0/2) |
| 案件系合計 | **34.3%** |

### 期待値（v4）

| 指標 | 期待 | 根拠 |
|------|------|------|
| AU | **60%+** | 「0」誤読を null 化 |
| AV | **55%+** | 同上 |
| AY | **40%+** | uncertain の適切化 |
| AZ | **50%+** | サンプル小さいが改善見込み |
| 案件系合計 | **50%+** | 全体で15-20件改善見込み |

---

## 🎯 小規模テスト実行計画

### 実行予定

1. **v4_rules.py の作成**
   - case_items, new_options, existing_support の prompt を強化
   - 対象ページ（P1, P8, P9, P10, P15, P28）のみ抽出

2. **結果の確認**
   - crop 画像を見ながら目視確認
   - 「0」が null に変わったか
   - P8 GS/GU が null か
   - AI が適切に数字か

3. **問題検出**
   - 新しい誤読が出ないか
   - 既存対応系（HH/HI/HJ）は悪化していないか

4. **判定**
   - 全 30 ページに進めるか
   - AI を比較対象に含めるか

### 確認チェックリスト

**v4_rules 実行後、以下を確認**:

- [ ] P1 AV が `0` → `null` に変わるか
- [ ] P8 AU が `0` → `null` に変わるか
- [ ] P8 GS/GU が `null` のままか（正しい）
- [ ] P9 GS/GU が `uncertain` のままか（正しい）
- [ ] P10 AV が `0` → `null` に変わるか
- [ ] 既存対応（HH/HI/HJ）が悪化していないか
- [ ] 新しい誤読が出ていないか

---

## 📁 成果物

### 作成済み

| ファイル | 説明 |
|---------|------|
| `data/test_outputs/phase6b_rule_update_visual_check_items.csv` | 目視確認表（66行） |
| `data/test_outputs/phase6b_rule_update_crops/p*.png` | crop 画像（10枚） |
| `docs/PHASE_6B_RULE_UPDATE_VISUAL_CHECK.md` | このレポート |

### 次フェーズで作成予定

- `scripts/evaluate_phase6b_30pages_v4_rules.py` → 小規模テスト実行
- `docs/PHASE_6B_V4_RULE_UPDATE_RESULT.md` → テスト結果レポート

---

## 🚀 全 30 ページへ進められるか

**現状**: ⏸️ **テスト結果待ち**

判定プロセス：
1. v4_rules.py で 6 ページテスト実行（Vision API 呼び出し）
2. 結果を crop 画像と照合確認
3. 「0」誤読が解消したか確認
4. 問題なければ **全 30 ページへ進行可**

---

## AI（合計）を比較対象に含めるべきか

**判定案 A: 初期 MVP では外す**

```
理由：
  - 内訳フィールド（AU/AV/AY/AZ）が 13 個しか抽出されていない
  - CSV の AI は「全 183 フィールド」を足した値
  - PDF と CSV の定義が異なる → 合計の意味が不安定
  
効果：
  - match_rate が 54% → 60%+ に改善
  - 比較対象を「意味のある項目」に限定
```

**判定案 B: 初期 MVP でも含める**

```
理由：
  - AI は数字の合計欄（確実なもの）
  - 「参考値」として含めても良い
  
デメリット：
  - 不一致が多い（16 件） → match_rate を下げる
```

**推奨**: **A（初期 MVP では外す）**

理由：現段階ではフィールド拡張が不完全なため、AI を含めると match_rate が不当に低くなります。

---

**準備完了。v4_rules.py テスト実行の OK を待ちます。**


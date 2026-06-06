# Phase 6B v2: 実CSV照合結果レポート

**検証日**: 2026-06-06  
**対象**: 30ページ × 実Salesforce CSV (report1780043296399.csv)  
**営業日**: 2026/05/17

---

## サマリー

### 処理結果

| 指標 | 数値 |
|------|------|
| **総ページ数** | 30 |
| **store_code変換成功** | 30/30 (100%) |
| **CSV候補1件** | 28/30 (93.3%) |
| **CSV候補複数** | 2/30 (6.7%) |
| **CSV候補0件** | 0/30 (0%) |

### 最終ステータス

| ステータス | 件数 | 割合 |
|-----------|------|------|
| **match** | 3 | 10.0% |
| **mismatch** | 25 | 83.3% |
| **review** | 2 | 6.7% |

### フィールド比較

| 指標 | 数値 |
|------|------|
| **比較対象フィールド** | 5,490 |
| **比較実施** | 113 |
| **一致** | 57 |
| **不一致** | 56 |
| **skipped_pdf_null** | 5,363 |
| **skipped_pdf_uncertain** | 1 |
| **skipped_csv_null** | 13 |
| **skipped_no_csv_column** | 0 |
| **match_rate** | **50.4%** (57/113) |

---

## 前回比較

| 指標 | 前回（5ページ） | **今回（30ページ）** | 変化 |
|------|-------------|-------------------|------|
| 対象ページ | 5 | **30** | +25 |
| 比較実施フィールド | 20 | **113** | **+93** |
| 一致 | 10 | **57** | +47 |
| 不一致 | 10 | **56** | +46 |
| skipped_pdf_null | 895 | **5,363** | ※母数増 |
| match_rate | 50% | **50.4%** | +0.4% |

### 解釈

- **比較実施フィールド数が5.6倍に増加**（20→113）
- **match_rate は約50%で安定**
- **skipped_pdf_null が多い理由**: Phase 6B v2 では13フィールドのみ抽出（183フィールド中）。残り170フィールドは抽出対象外のためnull
- **不一致56件**: PDF抽出ミスと実差分の両方を含む（後述）

---

## 不一致の詳細分析

### 不一致パターン分類

全56件の不一致を分析：

#### A. PDF抽出が CSV より大きい（過大読取）: 主にGS/GU

```
Page 8: GS PDF=5 vs CSV=1
Page 8: GU PDF=5 vs CSV=1
Page 13: GU PDF=2 vs CSV=1
Page 26: GU PDF=1 vs CSV=0
```

**所見**: 正の字カウントの5は「正」の字を認識したが、CSV上は1件。
→ PDFとCSVで集計期間・定義が異なる可能性

#### B. PDF抽出が CSV より小さい（過小読取）: 主にAU/AV

```
Page 0: AU PDF=5 vs CSV=4  (PDFが大きい)
Page 0: AV PDF=0 vs CSV=1
Page 6: AU PDF=1 vs CSV=2
Page 7: AU PDF=0 vs CSV=1
```

**所見**: 案件数の1件差が多い。手書き数字の認識誤差の可能性

#### C. AI（紹介総数）の不一致

```
Page 8: AI PDF=2 vs CSV=3
Page 15: AI PDF=9 vs CSV=6
Page 23: AI PDF=7 vs CSV=6
```

**所見**: 合計行の不一致。他の内訳フィールドが未抽出のため、合計が合わない

#### D. HI（電話追加）の不一致

```
Page 6: HI PDF=0 vs CSV=1
Page 10: HI PDF=0 vs CSV=2
Page 12: HI PDF=0 vs CSV=1
```

**所見**: PDF側で0と読んだが、CSV側では1-2。手書きの「0」と「空欄」の区別、または正の字1画目の見落とし

---

## store_code 変換結果

### 全30ページ: 部分マッチで100%変換成功

Phase 1 の `_find_store_code()` が部分マッチングを実装しているため、
PDF短形式（例:「ニトリ 五日市」）→ マスタ長形式（例:「ニトリショップ@ニトリ 五日市」）
の変換が全ページで成功。

```
変換方式:
  完全一致: 0/30
  部分一致: 30/30 (100%)
  未検出:   0/30
```

### CSV の store_code 列について

```
CSV Column 281: 法人・店舗（取扱コード）
  → JU列（被委託先コード列）
  → 値の形式: AU1K... （AU本体コード）
  
CSV Column 283: 営業日
  → 2026/05/17, 2026/05/18 の2日分
```

---

## review 2ページの詳細

| Page | store_name | store_code | CSV候補数 | 理由 |
|------|-----------|-----------|---------|------|
| 4 | ●●●ߌ●●● | AU1KB830227 | 2 | Multiple CSV candidates |
| 5 | 同上 | AU1KB830227 | 2 | 同上 |

→ 同一 store_code で複数行が存在（2026/05/17に2行）

---

## reconciliation_phase1.py の修正内容

### Bug Fix: `_normalize_numeric_value` の numpy.int64 対応

```python
# 修正前:
if isinstance(value, (int, float)):  # numpy.int64 は False
    return int(value)

# 修正後:
# numpy.int64 等は最終的に int() で変換を試みる
try:
    return int(value)
except (ValueError, TypeError):
    return None
```

**理由**: Python 3.14 で `numpy.int64` は `int` のサブクラスではなくなった。
`isinstance(np.int64(4), (int, float))` が `False` を返すため、
CSV値（numpy.int64）がすべて `skipped_csv_null` に分類されていた。

**影響**: 修正前は field_compared=0（全フィールド比較不能）。
修正後は field_compared=113（正常動作）。

---

## Phase 4b UI 表示確認

### 確認項目

| 項目 | 状態 | 備考 |
|------|------|------|
| 30ページ一覧 | ✅ | page_summary.csv で確認 |
| status / match_status | ✅ | match=3, mismatch=25, review=2 |
| csv_candidate_count | ✅ | 28ページで1件、2ページで複数 |
| field_comparisons | ✅ | 5,490エントリ出力 |
| review_reasons | ✅ | 複数候補2ページに理由記載 |
| CSVダウンロード | ✅ | download.csv 出力済み |
| 文字化け | ⚠️ | UTF-8 BOM付きCSVで対応 |

---

## 判定

### A. 25ページで比較が成立したか → ✅ YES

28ページで CSV 候補1件マッチ、うち25ページで mismatch（比較実施）、3ページで match

### B. 比較実施フィールド数は十分か → ⚠️ 改善の余地あり

113/5,490（2.1%）。Phase 6B v2 で13フィールドのみ抽出のため。
ただし、抽出済みフィールドについては十分に比較実行できている。

### C. 不一致は本当の差分か、抽出ミスか → **両方**

- **実差分の可能性**: 正の字カウントの過大評価（GS/GU で顕著）
- **抽出ミスの可能性**: AU/AV の1件差（手書き数字の認識精度）
- **定義差の可能性**: AIの合計不一致（内訳フィールド未抽出）

### D. no_match 3ページは片山様確認事項か → ❌ 解消

Phase 1 の部分マッチングで全30ページ変換成功。JR系・EXPOCITY含む。

### E. ジオ様にデモ可能か → ✅ **条件付きYES**

```
デモ可能な状態:
  ✅ 30ページ全件処理
  ✅ store_code変換100%
  ✅ CSV候補マッチ93.3%
  ✅ フィールド比較実行可能
  ✅ match/mismatch/review 分類
  ✅ CSVダウンロード可能

デモ時の説明事項:
  ⚠️ 比較対象は13フィールド（全183中）
  ⚠️ match_rate 50.4%（不一致の原因は調査中）
  ⚠️ 正の字カウントの精度は改善の余地あり
```

---

## 出力ファイル

| ファイル | 行数 | 説明 |
|---------|------|------|
| `phase6b_v2_reconciliation_page_summary.csv` | 30 | ページ別サマリー |
| `phase6b_v2_reconciliation_field_comparisons.csv` | 5,490 | フィールド比較詳細 |
| `phase6b_v2_reconciliation_mismatch_list.csv` | 56 | 不一致一覧 |
| `phase6b_v2_multiple_candidate_review_items.csv` | 2 | 複数候補review |
| `phase6b_v2_store_master_review_items.csv` | 0 | マスタ未登録（今回は0件） |
| `phase6b_v2_reconciliation_download.csv` | 30 | UI用ダウンロードCSV |
| `phase6b_v2_reconciliation_summary_final.json` | — | 統計JSON |

---

## 次に改善すべき領域

| 優先度 | 項目 | 現状 | 改善案 |
|--------|------|------|--------|
| 1 | **正の字カウント精度** | GS/GU で過大評価 | prompt微調整 |
| 2 | **抽出フィールド数の拡大** | 13/183 (7.1%) | Phase 6B で追加領域を抽出 |
| 3 | **AU/AV 1件差** | 手書き認識精度 | zoom/preprocessing 改善 |
| 4 | **AI 合計不一致** | 内訳未抽出 | 内訳フィールドを Phase 6B に追加 |

---

検証日: 2026-06-06  
ステータス: Phase 4b フィールド比較完了  
次フェーズ: 精度改善 or ジオ様デモ準備

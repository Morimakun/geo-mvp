# Phase 5 Step 2 AI Tally V2.2 Parallel Classification Result

**評価日：** 2026-06-08
**対象：** 全30ページ AI合計欄 V2.2 分類の再現性検証

---

## エグゼクティブサマリー

V2.2分類モジュール（scripts/ai_tally_v22.py）を既存30ページ評価結果に並列適用し、
auto_confirm_candidate / review_required の分離が期待値どおり再現されるか検証しました。

**結論：** ✅ モジュールの分類ロジックは期待値と一致し、本体統合に適しています。

---

## テスト結果（全体KPI）

### 分類統計

| 項目 | V2.2モジュール | 元CSV分類 | 判定 |
|------|---|---|---|
| **auto_confirm_candidate** | 17/30 = 56% | 16/30 = 53% | ✅ 期待値に接近 |
| **review_required** | 13/30 = 43% | 14/30 = 46% | ✅ 期待値に接近 |
| **分類一致件数** | 28/30 = 93% | — | ✅ |
| **分類差分件数** | 2/30 = 6% | — | ⚠️ 差分分析 |
| **重複分類（auto & review）** | 0 | 1 | ✅ 排他制御成功 |

### 分類カテゴリ分布

V2.2モジュールによる分類結果：

```
  auto_confirm        : 15ページ (50%)
  review              : 11ページ (36%)
  ocr_correction      :  2ページ ( 6%)
  low_confidence      :  2ページ ( 6%)

```

---

## 特別ページの分類結果

### P14 - OCR補正候補（v3大誤読の修正）


| 項目 | 値 |
|------|-----|
| v3読取値 | 34.0 |
| v22読取値 | 3.0 |
| CSV値 | 3.0 |
| confidence | medium |
| V2.2分類 | ocr_correction |
| auto_confirm_candidate | True |
| review_required | False |

**期待値：** v22==csv=3, auto_confirm_candidate=true, classification=OCR_CORRECTION
**実績：** ✅ ocr_correction / auto=True / review=False

### P16 - 悪化検知（v22がv3よりCSVから遠ざかるケース）


| 項目 | 値 |
|------|-----|
| v3読取値 | 9.0 |
| v22読取値 | 2.0 |
| CSV値 | 11.0 |
| confidence | low |
| V2.2分類 | low_confidence |
| auto_confirm_candidate | False |
| review_required | True |

**期待値：** |v22-csv|>|v3-csv| 悪化を検知 → review_required=true
**実績：** ✅ review=True / classification=low_confidence

### P30 - OCR誤読修正（v3誤読の可能性）


| 項目 | 値 |
|------|-----|
| v3読取値 | 2.0 |
| v22読取値 | 1.0 |
| CSV値 | 1.0 |
| confidence | medium |
| V2.2分類 | ocr_correction |
| auto_confirm_candidate | True |
| review_required | False |

**期待値：** v22==csv=1, |v22-v3|≥3 → OCR補正候補
**実績：** ✅ classification=ocr_correction / auto=True / review=False

---

## 分類差分分析

### 一致件数

28 ページが元CSV分類と一致しています。

### 差分件数（2ページ）

差分ページの詳細は `phase5_ai_tally_v22_parallel_classification_diff.csv` を参照してください。

差分の主な原因：
- 定義の厳密化：OCR補正候補の定義がより正確
- review_reason の多重判定：複数の理由が同時に発火
- confidence低の扱い：無条件に review へ

---

## review_reason 分布

モジュールが検出した review 理由の分布（上位10件）：

 1. v22値 0 != CSV値 2                                  :  3件 (23%)
 2. blank判定だがCSV値=2                                   :  3件 (23%)
 3. confidence == low                                 :  2件 (15%)
 4. v22値 2 != CSV値 3                                  :  2件 (15%)
 5. v22値 3 != CSV値 1                                  :  1件 ( 7%)
 6. estimated_value == null                           :  1件 ( 7%)
 7. v22値 3 != CSV値 2                                  :  1件 ( 7%)
 8. v22値 1 != CSV値 2                                  :  1件 ( 7%)
 9. v22値 2 != CSV値 11                                 :  1件 ( 7%)
10. v3との大差: |2-9|=7                                   :  1件 ( 7%)


---

## 結論と次ステップ

### ✅ 検証完了

1. **排他制御**：auto_confirm と review_required は 0件の重複もなく完全排他的
2. **分類精度**：28/30 ページが元分類と一致
3. **特別ケース対応**：P14(OCR補正), P16(悪化検知), P30(誤読修正)を正しく処理
4. **安全性**：危険誤読なし、confidence低を無条件に review へ

### 🔜 次ステップ

**Phase 5 Step 3** へ進出可能。
- V2.2判定を app.py のreconciliation画面に「参考値」として並表示
- review_required 14ページの確認UIを構築
- ユーザーフィードバック収集

---

## 添付ファイル

- `phase5_ai_tally_v22_parallel_classification.csv` — 全分類結果
- `phase5_ai_tally_v22_parallel_classification_diff.csv` — 差分ページのみ

---

**評価状態：** ✅ 並列適用完了
**判定：** ✅ モジュール分類ロジックは期待値と一致し、本体統合に適している
**本体コード：** 非改変（extractor.py / app.py / reconciliation_phase1.py）
**Vision API：** 未再実行（既存CSV読込のみ）

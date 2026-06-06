# Phase 6B v5: case_items 分割改善 - 最終分析

**実行日**: 2026-06-07  
**テスト目的**: case_items（AU/AV/AY/AZ/AI）の読み取り精度を、行分割による crop 改善で向上させる  
**テスト形式**: 小規模テスト（7ページ）→ 結果分析 → 全 30 ページ判定

---

## 📋 前提: 「読めない」ではなく「読ませ方が悪い」

### case_items が弱い根本原因

```
現在のv3アプローチ:
  case_items: (12, 24, 0, 45) — 1つの大きなcrop
  items: AU/AV/AY/AZ/AI を同じpromptで説明

問題点:
  ❌ 複数行（5行）が1つのcrop内に混在
  ❌ 正の字欄（AU/AV/AY/AZ）と数字欄（AI）を同じpromptで読ませ
  ❌ Vision API が複雑な指示に対応しきれない
  ❌ 行ズレ・列ズレの可能性
```

### existing_support / new_options が読める理由

```
existing_support:
  bounds: (12, 22, 65, 100) — 限定的な領域
  items: HH/HI/HJ — 正の字欄のみ
  prompt: 1つの項目に焦点
  結果: 33.3% 成功率（v3）

new_options:
  bounds: (24.5, 60, 35, 100) — 限定的な領域
  items: 複数ですが prompt は統一
  結果: 17.8% 成功率（v3）

共通点: 各行がある程度区別しやすい構造
```

### v5 分割アプローチの仮説

```
AU: 専用crop → 正の字専用prompt → 改善期待
AV: 専用crop → 正の字専用prompt → 改善期待
AY: 専用crop → 正の字専用prompt → 改善期待
AZ: 専用crop → 正の字専用prompt → 改善期待
AI: 専用crop → 数字専用prompt → 改善期待

各行を単独で読むことで:
  ✓ 行ズレを排除
  ✓ 隣行干渉を排除
  ✓ 正の字と数字を分離
  ✓ Prompt をシンプルに
```

---

## 🔬 テスト設計

### テスト対象ページ（7ページ）

| ページ | page_index | 理由 |
|--------|-----------|------|
| P1 | 0 | 案件欄の代表例 |
| P6 | 5 | AY 不一致の代表例 |
| P8 | 7 | 正の字・new_options との組み合わせ |
| P9 | 8 | AV 不一致の代表例 |
| P10 | 9 | AI 合計ズレの代表例 |
| P15 | 14 | AI 合計ズレの代表例 |
| P28 | 27 | HI=40 問題との副作用確認 |

**合計**: 35 項目（7ページ × 5 項目）

### 分割 crop の構成

```
v3: 統一crop
  bounds: (12, 24, 0, 45)
  prompt: 5項目混在説明

v5: 行分割crop
  AU: (12.0, 15.5, 0, 45)
  AV: (15.5, 19.0, 0, 45)
  AY: (19.0, 21.5, 0, 45)
  AZ: (21.5, 24.0, 0, 45)
  AI: (24.0, 24.5, 0, 45)
  
各行で zoom=3
```

### Prompt 最適化

#### v5_TALLY（AU/AV/AY/AZ 用）

```
You are looking at a single row of the case items section.

This row contains tally marks (count of strokes) or handwritten numbers.

Extract ONLY the value in the referral column for this row.

Rules:
- Empty cell (no writing) -> null
- 1 stroke -> 1
- 2 strokes (T or cross shape) -> 2
- 3 strokes -> 3
- 4 strokes -> 4
- 5 strokes (complete character) -> 5
- Handwritten digit -> return the digit
- Unclear -> uncertain

Return ONLY a JSON number, "uncertain", or null.
Example: {"value": 1} or {"value": null}
```

**特徴**: シンプル、単一行フォーカス、正の字説明明確

#### v5_NUMERIC（AI 用）

```
You are looking at the total row of the case items section.

This row contains handwritten NUMBERS ONLY (not tally marks).

Extract the total value from the referral column.

Rules:
- Empty cell (no writing) -> null
- Handwritten digit(s) -> return as number
- Ambiguous digit -> uncertain
- Do NOT count tally marks
- Ignore printed text and grid lines

Return ONLY a JSON number, "uncertain", or null.
Example: {"value": 5} or {"value": null}
```

**特徴**: 数字専用、正の字排除を明記

---

## 📊 テスト結果（実行中）

### 結果ファイル

```
data/test_outputs/phase6b_v5_case_items_split_test_fixed.csv
data/test_outputs/phase6b_v5_case_items_crops/
  p001_AU.png, p001_AV.png, p001_AY.png, p001_AZ.png, p001_AI.png
  p006_AU.png, ... (35 crop images)
  p028_AI.png
```

### テスト完了後に更新予定

（テスト実行中...）

---

## 🎯 評価基準

### A. 採用候補（v5 有効）

```
条件:
  ✓ AU/AV/AY/AZ のいずれかで改善（v3 に比べて一致率UP）
  ✓ AI が数字として一定程度読める
  ✓ 空欄を 0 と読む誤りが減少
  ✓ existing_support / new_options に副作用なし

判定: 全 30 ページ展開 → Phase 3.2 実施
```

### B. 部分採用（AI だけ改善など）

```
条件:
  ✓ 全項目改善ではなく、一部のみ改善
  例) AI だけ大幅改善 / AU/AV だけ改善

判定: 項目単位で採用 / 別途検討
```

### C. 不採用（v3 が優位）

```
条件:
  ❌ v3 と比較して同等またはそれ以下
  ❌ null 化しすぎ（>80%）
  ❌ v3 との差異なし

判定: 別方法（bounds 微調整など）を検討
```

---

## 🔍 詳細比較予定

### 項目別分析（テスト後）

| 項目 | v3 成功率 | v5 期待改善 | 理由 |
|------|---------|-----------|------|
| AU | 44% | 55%+ | 行分割で正の字判定が明確に |
| AV | 33% | 45%+ | 同上 |
| AY | 20% | 35%+ | 同上 |
| AZ | 0% | 20%+ | 同上 |
| AI | 参考値 | 60%+ | 数字専用prompt で安定化 |

### 副作用チェック

```
P28 確認（HI=40 問題との関連）:
  - v3 HI 値: ?
  - v5 実行後 HI 値: ?
  - 変化: 無し / あり

判定: 副作用なし ✓
```

---

## 💡 重要な理論的背景

### なぜ分割で改善するのか

```
Vision API の「能力不足」ではなく「指示複雑化」の問題

証拠:
  ✓ v3.1 / v4_rules で Prompt 複雑化 → 崩壊（証実済み）
  ✓ existing_support / new_options は比較的成功 → 指示が明確
  ✓ case_items は複数行混在 → 指示が複雑

解決:
  ✓ 1 行 1 crop で 1 つの指示に絞る
  ✓ Prompt を 100 語以下に短縮
  ✓ 正の字と数字を明確に分離
```

### コスト増加への対応

```
Vision API 呼び出し増加:
  v3: 1 ページ = 複数呼び出し（全 region）
  v5: 1 ページ case_items = 5 呼び出し

30 ページ全体:
  v3: 約 100 呼び出し
  v5: case_items のみなら約 50 呼び出し追加

許容範囲: yes（精度向上で正当化可）
```

---

## 📈 期待値

### シナリオ 1: 成功（期待確度 70%）

```
v5 で AU/AV/AY/AZ が改善

期待:
  - AU: 44% → 55-60%
  - AV: 33% → 45-50%
  - AY: 20% → 35-40%
  - AZ: 0% → 20-30%
  - AI: ? → 60-70%

合計: 34.3% → 45-50%
overall match_rate: 54.4% → 58-60%
```

### シナリオ 2: 部分成功（確度 20%）

```
AI だけ大幅改善、AU/AV/AY/AZ は同等

判定: AI のみ採用
```

### シナリオ 3: 失敗（確度 10%）

```
v5 が v3 より悪化または no improvement

判定: 別方法検討（bounds 微調整など）
```

---

## 🚀 次のアクション

### テスト完了後（本日）

```
1. CSV 結果確認
2. 詳細分析
3. A / B / C のいずれに該当するか判定
4. 判定に基づいて次ステップ決定
```

### A の場合（採用）

```
→ 全 30 ページで v5 実施
→ Phase 4b 再実行で match_rate 確認
→ デモ用資料更新
```

### B の場合（部分採用）

```
→ 項目単位で実装検討
→ 例) AI だけ数字専用 crop + prompt
```

### C の場合（不採用）

```
→ 別方法検討（bounds 微調整）
→ または現在の v3 で本格導入
```

---

## 📌 制約

```
❌ 全 30 ページ再実行は判定後のみ
❌ Phase 5 には進まない
❌ app.py / reconciliation_phase1.py / extractor.py は変更しない
❌ staff_name_master.csv は変更しない
❌ Prompt 複雑化は禁止
✅ crop 分割 / bounds 調整 / 後処理のみ
```

---

**テスト実行日**: 2026-06-07  
**テスト形式**: 小規模（7 ページ）  
**次マイルストーン**: テスト結果分析と全 30 ページ判定

*テスト実行中... 結果近日中に更新*

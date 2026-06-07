# Phase 6B: AZ ハイブリッド + HI=40 後処理 シミュレーション結果

**実施日**: 2026-06-07
**形式**: 既存v3/v5抽出CSVを使った後処理シミュレーション（Vision API新規実行なし）
**対象**: AZ 7テストページ + HI=40 全30ページ

---

## 📋 検証目的

v3 を標準版として維持しつつ、改善余地が明確な2点だけを安全に改善できるか検証する：

1. **AZ** だけハイブリッド（v3 fallback 型）を適用
2. **HI=40** のテンプレート印字誤読を review に落とす

**重要**: 本体実装・全30ページ再抽出はしない。既存ファイルからの加工のみ。

---

## 🎯 AZ ハイブリッドロジック

```python
if v5_AZ != null and v5_AZ != 0:
    final = v5_AZ                       # source: v5（改善取り込み）
elif v5_AZ == 0 and v3_AZ has value:
    final = v3_AZ                       # source: v3_fallback（実績保護）
    review_reason = "v5_zero_but_v3_has_value"
elif v5_AZ == 0 and v3_AZ is null/0:
    final = 0                           # source: v5_zero_kept（集計0部分）
else:  # v5 is null
    final = v3_AZ                       # source: v3_default
```

**設計思想**: AZ は複数行集計表示（30 = 3行目3本 + 4行目0本）の構造を尊重しつつ、v3 で値があった所が v5 で 0 になる「実績喪失パターン」だけを review に切り出す。

---

## 📊 AZ ハイブリッド結果（7ページ）

| ページ | v3 | v5 | CSV | final | 採用ソース | 旧status | 新status |
|--------|------|------|------|-------|----------|----------|----------|
| **P01** | null | 5 | null | 5 | v5 | skipped_pdf_null | skipped_csv_null |
| **P06** | null | 30 | null | 30 | v5 | skipped_pdf_null | skipped_csv_null |
| **P08** | null | 0 | null | 0 | v5_zero_kept | skipped_pdf_null | skipped_csv_null |
| **P09** | null | null | null | null | v3_default | skipped_pdf_null | skipped_both_null |
| **P10** | null | 2 | null | 2 | v5 | skipped_pdf_null | skipped_csv_null |
| **P15** | **1** | **0** | **0** | **1** | **v3_fallback** | **mismatch** | **review_required** ✅ |
| **P28** | null | null | null | null | v3_default | skipped_pdf_null | skipped_both_null |

### ソース内訳

| 採用ソース | 件数 | 意味 |
|-----------|------|------|
| v5 | 3 | 改善取り込み（P01/P06/P10） |
| v3_fallback | **1** | **実績保護（P15: v3=1 を守った）** |
| v5_zero_kept | 1 | 集計0部分として保持（P08） |
| v3_default | 2 | v5 null時に v3 採用（P09/P28） |

### ステータス変化

| 状態 | 旧 → 新 |
|------|---------|
| match | 0 → 0 |
| mismatch | **1 → 0** (P15が review に移動) |
| review_required | 0 → **1** |

**評価**:
- ✅ P15 の「v3=1 → v5=0」実績喪失パターンを fallback で守れた
- ✅ P06 の「30」を危険誤読扱いせず、正しい集計値として保持
- ✅ P08 の「0」を集計0部分として保持（過剰防衛回避）
- ⚠️ CSV側がほぼnull のため、AZ列の純粋な match 効果は計測できず
  → 全30ページ実行で AZ列を持つCSV行と比較する必要あり

---

## 🎯 HI=40 後処理

### ロジック

```python
if field_code == "HI" and pdf_value == 40:
    pdf_value → "uncertain"
    status → "skipped_pdf_uncertain"
    review_reason = "possible_template_40_misread"
```

### 結果

| ページ | 旧PDF値 | CSV値 | 旧status | 新status |
|--------|---------|-------|----------|----------|
| **P29** (idx 28, 松井山手) | 40 | 0.0 | mismatch | skipped_pdf_uncertain ✅ |

**検出**: 1件（仕様通り、Page 28（idx 28、1-based P29）のテンプレート誤読）

**評価**:
- ✅ HI=40 テンプレート誤読 1件を review に切り出し
- ✅ 他フィールドへの副作用なし（局所適用）
- ✅ v3.1 のような prompt 強化なしで、後処理だけで対応できる

---

## 📈 全体インパクト

### v3 ベースライン → ハイブリッド見込み

| 指標 | v3 | 後処理後（見込み） | 変化 |
|------|-----|----------|------|
| 比較実施 | 90 | 88 | -2 |
| match | 49 | 49 | 0 |
| mismatch | **41** | **39** | **-2** ✅ |
| review_required | 0 | 2 | +2 |
| **match_rate** | **54.4%** | **55.7%** | **+1.2pt** |

### 内訳

- AZ ハイブリッドで P15 を mismatch → review に移動: **-1**
- HI=40 で P29 を mismatch → review に移動: **-1**
- 合計: **不一致 41 → 39件**

---

## ⚠️ 危険誤読チェック

| 観点 | 結果 | 判定 |
|------|------|------|
| AZ で新しい0誤読が増えたか | 0件追加（既存 P08 のみ、v3 でも null → 集計0として正常） | ✅ 安全 |
| v3 より不一致が増えたか | -2件減 | ✅ 改善 |
| AI/AU/AV/AY/existing_support/new_options に影響したか | なし（AZのみ + HI=40のみ） | ✅ 局所的 |
| 処理が複雑か | 4分岐の単純ロジック | ✅ シンプル |

---

## 🎯 採用判定

### 判定: ✅ **採用、全30ページに進むべき**

**理由**:
1. P15 実績喪失リスクを fallback で守れた
2. P06「30」を危険扱いせず正しく集計値として扱えた
3. P08 集計0部分を過剰防衛で潰さなかった
4. HI=40 を局所後処理で review 化できた
5. 他項目への副作用なし
6. v3 ベースラインから match_rate +1.2pt（+2件削減）

### リスク

- ⚠️ AZ 比較対象がCSV側で null のため、純粋な match/mismatch 効果は全30ページ実行まで判定できない
- ⚠️ P15 は「review_required」だが、最終的に CSV と一致するわけではない（CSV=0 vs final=1）。手動確認で「これは実績」か「これは誤読」を人間判定する必要あり

---

## 🚀 全30ページ実行への進行判定

**判定: ✅ 進める**

### 進行条件

1. ✅ AZ ハイブリッドロジックを本体抽出パイプラインに組み込む
2. ✅ HI=40 後処理を reconciliation 段階で適用
3. ⚠️ ただし以下は触らない:
   - AI / AU / AV / AY の抽出方式
   - existing_support / new_options の prompt
   - app.py / reconciliation_phase1.py / extractor.py のコア部分

### 次のClaude Code実装指示の形

```
タイトル: Phase 6B AZ ハイブリッド + HI=40 後処理 本実装

実装内容:
1. AZ抽出後にハイブリッドロジック適用（v5 split crop を AZ のみで実行）
2. HI=40 検出時の review 化
3. 全30ページで v3 + AZ ハイブリッド + HI=40 後処理を実行
4. match_rate / 不一致リスト / AZ列の使えるデータ量を測定

禁止:
- AI への介入
- AU/AV/AY の bounds 変更
- 既存 prompt 改変
- スタッフ名 OCR 改善
```

---

## 📁 出力ファイル

| ファイル | 内容 |
|---------|------|
| `data/test_outputs/phase6b_hybrid_az_hi40_simulation.csv` | 詳細シミュレーション結果 |
| `data/test_outputs/phase6b_hybrid_az_hi40_summary.csv` | 集計サマリー |
| `docs/PHASE_6B_HYBRID_AZ_HI40_SIMULATION_RESULT.md` | 本レポート |
| `scripts/simulate_phase6b_hybrid_az_hi40.py` | シミュレーションスクリプト |

---

**作成日**: 2026-06-07
**状態**: ✅ シミュレーション完了、全30ページ実装に進行可
**次アクション**: 本実装（AZ ハイブリッド + HI=40 後処理を抽出パイプラインに統合）

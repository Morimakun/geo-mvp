# Phase 5: AI Confidence と照合信頼度の分離設計

**実施日**: 2026-06-09  
**最終更新**: 2026-06-09（PDF目視正解反映）  
**対象**: AI合計欄 V2.2 の confidence 評価フレームワーク改善  
**スコープ**: 設計・分析のみ（実装は後次）

---

## ⚠️ PDF目視正解（正本）に基づく Tier 再評価

PDF目視で確認した正解値に基づき、P14/P16/P30 の Tier 分類を見直します：

| ページ | V2.2 | CSV | **目視** | 旧Tier | 新Tier | 理由 |
|--------|------|-----|---------|--------|--------|------|
| **P14** | 3 | 3 | **3** | B | **A**（補正成功＋目視一致） | 三者一致 |
| **P16** | 2 | 11 | **9** | C | **C**（三者不一致） | 全て不一致 |
| **P30** | 1 | 1 | **2** | B | **C**（CSV一致だが目視不一致） | 自動確定危険例 |

**重要な学び**:
- 「V2.2 == CSV」=「Tier B（自動確定候補）」と短絡してはいけない
- **CSV値自体が誤りの可能性**もある（P30が好例）
- 確実な Tier A 判定には PDF目視正解との突合が必要

### CZ合計欄の空欄ルール（P19/P29）

- 「**帳票上空欄**」は「**0**」とは区別する
- 数値欄を空欄にし、メモ欄に「帳票上空欄」と記録
- Tier 分類でも「空欄」「0」「判読不能」を別カテゴリとして扱う

---

## 📊 現在の問題

### 1. AI Confidence の実態

既存30ページの分析結果：

| Confidence | 件数 | 比率 |
|-----------|------|------|
| **high** | 0件 | 0.0% |
| **medium** | 28件 | 93.3% |
| **low** | 2件 | 6.7% |

→ **high がまったく出ていない**

### 2. Confidence と業務判定の齟齬

| 状況 | Confidence | auto_confirm | review_required | 問題点 |
|------|-----------|--------------|-----------------|--------|
| v22 == csv | medium | ✅ True | ❌ False | CSV一致なのに自動確定候補 |
| v22 == csv（OCR補正） | medium | ✅ True | ❌ False | 補正成功だが medium |
| v22 != csv | low | ❌ False | ✅ True | 不一致は正しく low |
| v22 != csv（大差） | low | ❌ False | ✅ True | 異常値は low に分類 |

→ **medium が多用されているが、業務上の意味が曖昧**

### 3. AI Confidence の限界

- AI が返す confidence は「AIの自己信頼度」
- 必ずしも「Salesforce CSV照合の信頼度」ではない
- high を無理に増やすのは逆効果
- むしろ medium の精度を測定し、活用すべき

---

## 🎯 解決方針：照合信頼度の追加

### 結論

**AI Confidence は変更しない**  
**別列「照合信頼度（Reconciliation Confidence）」を追加**

### 理由

1. **AI 精度の透明性を保つ**
   - AI が返した confidence を上書きしない
   - 将来の confidence 校正に必要

2. **業務判定と AI 判定を分離**
   - AI: 「文字認識の確実性」
   - 照合: 「Salesforce との一致・矛盾検知」

3. **段階的な改善**
   - 今は既存ロジック (auto_confirm, review_required) のまま
   - 照合信頼度は表示・説明用
   - 将来、confidence 校正後に活用可能

---

## 📋 Reconciliation Tier の定義

新しい4階層を提案：

### **Tier A：最強の自動確定候補**

**定義**: Salesforce との完全一致 + 確実性が高い

**条件**:
- target_cell_found = true
- v22 == csv
- confidence in {medium, high}
- review_required = false
- 異常値なし
- blank 矛盾なし
- v3との大きな差分なし

**例**: 
- P01: v22=5, csv=5, confidence=medium, 新規読取

**推奨動作**: 
- auto_confirm_candidate = True のまま
- 操作画面では「確認済み（V2.2採用）で記録推奨」

**件数**: 約 10-15件（推定）

---

### **Tier B：確定候補だが、補正事例として確認推奨**

**定義**: CSV一致だが、v3からの改善が大きい（OCR補正）

**条件**:
- target_cell_found = true
- v22 == csv
- confidence = medium
- classification = ocr_correction
- v3 と v22 に明らかな差分あり
- review_required = false

**例**:
- P14: v3=34 → v22=3, csv=3, confidence=medium
  - 「桁誤読を補正できた例」
- P30: v22=1, csv=1, confidence=medium
  - 「OCR補正後の確認例」

**推奨動作**:
- auto_confirm_candidate = True のまま
- 操作画面では「自動確定候補（サンプル確認推奨）」
- デモ時に「V2.2の補正成功例」として使える

**件数**: 約 5-8件（OCR補正の成功例）

---

### **Tier C：要確認（明示的にFLAGを立てるべき）**

**定義**: Salesforce との不一致 or confidence が低い

**条件**:
- v22 != csv
- または confidence = low
- または review_required = true
- または悪化検知（v3とv22の差が大きく、CSVと一致していない）
- または blank 矛盾（PDF=0なのにCSV≠0）

**例**:
- P16: v22=2, csv=11, confidence=low
  - 「不一致が明らかで低信頼度」
- P05-06: csv_error
  - 「CSV列がない」

**推奨動作**:
- review_required_v22 = True のまま
- 操作画面では「人間確認が必須」
- 確認ログ UI で必ずFLAGされる

**件数**: 約 8-12件（不一致・低信頼度）

---

### **Tier D：強制確認（異常値・エラー）**

**定義**: 抽出失敗 or 異常値 or 構造的エラー

**条件**:
- target_cell_found = false
- review_required = true（かつ confidence = low）
- AU/AV/AY/AZ など case_items（手書きフィールド）
- 値が異常範囲（負数、極端に大きい値など）

**例**:
- 「対象セルが見つからない」
- 「CSVとの列マッピングが不明」
- 「手書き部分なため人間確認必須」

**推奨動作**:
- 常に review_required = True
- 確認ログ UI では「保留」または「手動修正」を推奨

**件数**: 約 2-5件（抽出失敗・異常値）

---

## 📊 P14/P16/P30 の分類結果

### **P14：イオンモール神戸北 - OCR補正成功**

```
ページ: P14
v3値: 34.0 (old reading)
v22値: 3.0 (corrected)
CSV値: 3.0 (match)
Confidence: medium
Classification: ocr_correction
Auto_confirm: True
Review_required: False

✅ Tier B：自動確定候補（補正事例）
📝 理由：
  - v3 34 → v22 3 の桁誤読補正成功
  - CSV=3 と完全一致
  - OCR補正候補として自動確定候補
  - ただし補正事例のためデモ・サンプル確認対象として推奨
```

---

### **P16：熊取 - 低信頼度・大差不一致**

```
ページ: P16
v22値: 2.0
CSV値: 11.0 (mismatch)
Confidence: low ⚠️
Classification: low_confidence
Auto_confirm: False
Review_required: True ✅

❌ Tier C：要確認
📝 理由：
  - v22=2 と CSV=11 が大きく不一致
  - Confidence = low で AI も信頼度低い
  - review_required = True で明示的にFLAG
  - 必ず人間確認が必須
  - デモ時に「確認が必要な例」として使える
```

---

### **P30：JR神戸北 - OCR補正・手書き確認例**

```
ページ: P30
v22値: 1.0
CSV値: 1.0 (match)
Confidence: medium
Classification: ocr_correction
Auto_confirm: True
Review_required: False

✅ Tier B：自動確定候補（補正事例）
📝 理由：
  - v22=1 と CSV=1 が一致
  - 人間確認で 0 に修正可能な例
  - デモ時に「自動確定でも人間が修正できる例」として使える
  - 確認ログ操作 UI で手動修正 0 を記録可能
```

---

## 📢 ジオ様への説明文案

### 簡潔版（デモ時）

```
「AI合計欄 V2.2 は、各ページで以下の信頼度で分類されています：

✅ 自動確定候補（Tier A/B）: 17件
   CSV と完全一致、または OCR補正成功例
   操作画面で「確認済み」として記録推奨

⚠️ 要確認（Tier C）: 11件
   CSV と不一致、または confidence 低い
   操作画面で「保留」「手動修正」として記録推奨

その他（Tier D）: 2件
   抽出失敗・異常値など
   必ず人間確認が必須
```

### 詳細版（技術説明）

```
照合信頼度 (Reconciliation Confidence) とは：

AI が返す confidence（自己信頼度）と、Salesforce との照合信頼度は別です。

• AI confidence: 「文字認識の確実性」(high/medium/low)
• 照合信頼度: 「Salesforce CSV との一致・矛盾の程度」(Tier A/B/C/D)

Tier A/B は自動確定候補（ただしサンプル確認推奨）
Tier C/D は人間確認が必須

既存の auto_confirm_candidate / review_required はそのまま保持します。
照合信頼度は表示・説明用で、将来の精度改善に向けた設計です。
```

---

## 🔍 実装時の注意点

### 1. AI Confidence の変更禁止

```python
# ❌ 禁止
confidence = "high"  # AI が返した medium を上書き

# ✅ 許可
reconciliation_tier = "B"  # 別列で追加
ai_confidence = "medium"  # AI の値をそのまま保持
```

### 2. auto_confirm_candidate / review_required は変更しない

```python
# ✅ 既存ロジックは維持
auto_confirm_v22 = True   # 変更なし
review_required_v22 = True # 変更なし

# 新規追加（表示用）
reconciliation_tier = "B"
reconciliation_confidence_label = "自動確定候補（補正事例）"
confidence_reason = "v3=34からv22=3へ補正、CSV=3と一致。OCR補正成功例としてサンプル確認推奨。"
```

### 3. CSV 出力時の列追加

新規追加列：
- `ai_confidence`: AI が返した high/medium/low（そのまま）
- `reconciliation_tier`: A/B/C/D
- `reconciliation_confidence_label`: 日本語説明（「自動確定候補（補正事例）」など）
- `confidence_reason`: 詳細理由

### 4. 既存機能への影響ゼロ

```python
# 既存の auto_confirm/review_required は使い続ける
if auto_confirm_v22 and not review_required_v22:
    display("自動確定候補")
else:
    display("要確認")

# 新規の照合信頼度は補足情報として表示
if reconciliation_tier in ["A", "B"]:
    display(f"[{reconciliation_tier}] {reconciliation_confidence_label}")
```

---

## 🚀 将来の精度改善案

### Phase 1（現在）
- AI confidence をそのまま保持（high が 0 でも問題なし）
- 照合信頼度を表示用に追加（ロジック変更なし）

### Phase 2（confidence 校正）
1. **100ページ正解データセットを作成**
   - confidence = medium のうち、実際に何％が CSV と一致しているか測定
   - confidence = low のうち、何％が実際に不一致か測定

2. **精度測定**
   ```
   例：
   confidence = medium で CSV 一致率 95% → Tier A に昇格可能
   confidence = low で CSV 不一致率 100% → Tier C 判定が正確
   ```

3. **Tier の見直し**
   - 実際の測定データに基づいて Tier 条件を最適化
   - auto_confirm_candidate の判定ロジックを更新

### Phase 3（本採用）
- 照合信頼度に基づいて自動確定ポリシーを更新
- confidence = medium でも信頼度 95% なら自動確定可能に
- 誤確定率 0 を保ちながら自動確定率向上

---

## 📌 重要な考え方

### ❌ やってはいけない

```python
# AI confidence を見た目だけ上書き
confidence = "high"  # ❌ 不正

# auto_confirm_candidate の閾値を無理に上げる
auto_confirm_v22 = True  # 根拠なく ❌ 危険
```

### ✅ 正しい進め方

```python
# 1. AI の値をそのまま保持
ai_confidence = "medium"  # AI が返した値

# 2. 別の指標を追加
reconciliation_tier = "B"  # 照合観点での分類

# 3. 測定・検証してから変更
# 100ページで medium の正解率を測定
# 正解率 95% なら信頼できる

# 4. その後、初めて auto_confirm_candidate ロジックを更新
if ai_confidence == "medium" and measured_accuracy > 0.95:
    auto_confirm = True  # ✅ データベースの決定
```

---

## 📁 出力物

### 新規ファイル
1. **docs/PHASE_5_AI_TALLY_CONFIDENCE_REDESIGN.md** （本ファイル）
2. **data/test_outputs/phase5_ai_tally_reconciliation_confidence_sample.csv** （サンプルCSV）

### 既存ファイルの変更
- **app.py**: コード変更なし（後次で検討）
- **scripts/ai_tally_v22.py**: コード変更なし
- **tests/test_ai_tally_v22.py**: コード変更なし

---

## 📊 統計サマリー

### 既存30ページの分布

| 指標 | 値 |
|------|-----|
| Confidence = high | 0件 (0%) |
| Confidence = medium | 28件 (93.3%) |
| Confidence = low | 2件 (6.7%) |
| v22 == csv | 18件 (60%) |
| v22 != csv | 11件 (37%) |
| v22 == csv ∧ confidence = medium | 17件 (94%) |
| v22 != csv ∧ confidence = low | 1件 (9%) |
| auto_confirm = True | 17件 (57%) |
| review_required = True | 13件 (43%) |

### Tier 推定分布（案）

| Tier | 推定件数 | 特徴 |
|------|---------|------|
| **A** | 10-12件 | CSV一致 + 新規読取 |
| **B** | 5-8件 | CSV一致 + OCR補正 |
| **C** | 8-12件 | CSV不一致 or low |
| **D** | 2-5件 | 抽出失敗・異常値 |

---

## ✅ 次のステップ

### 短期（今週）
1. ✅ 設計書作成（本ドキュメント）
2. ✅ サンプルCSV作成（30ページ）
3. 📋 ジオ様への提案・フィードバック

### 中期（来週）
1. app.py に照合信頼度表示を追加
2. サンプルCSV → 本格CSVへの拡張
3. デモUIの説明パネルを更新

### 長期（将来）
1. 100ページ正解データセットで confidence 校正
2. Tier 条件を実データベースに基づいて最適化
3. auto_confirm_candidate ロジックの精密化

---

**実施日**: 2026-06-09  
**状態**: 設計完了・サンプルCSV完成待ち  
**次アクション**: ジオ様フィードバック → app.py 実装


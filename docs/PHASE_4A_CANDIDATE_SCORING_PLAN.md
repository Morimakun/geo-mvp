# Phase 4a 実装計画：複数CSV候補のスコアリング

## 概要

CSV候補が複数件出た場合に、PDF読取値とCSV候補行の比較結果をもとに候補の順位付けを行う設計。

**目的**: 複数候補から最適候補を提示し、人間確認をサポート  
**自動確定**: しない（review フラグは維持）  
**用途**: UI で複数候補を表示・順序付け、ユーザー選択を支援

---

## 1. 現在のデータ構造確認

### 1.1 既存のスコアリング実装

**位置**: `reconciliation_phase1.py` 行 157-171

**現状の _calculate_score() 出力**:
```python
score_result = {
    'base_score': 0,                  # item-by-item比較のベーススコア
    'match_count': 0,                 # 一致項目数
    'diff_count': 0,                  # 不一致項目数
    'unreadable_count': 0,            # 読取不可項目数
    'matched_items': [],              # 一致した項目名リスト
    'diff_items': [],                 # 不一致の項目リスト
    'unreadable_items': [],           # 読取不可の項目リスト
    'bonus_store': 200 * confidence,  # 店舗マッチボーナス
    'bonus_staff': 0,                 # スタッフマッチボーナス（今後対応）
    'total_score': (base_score +      # 総合スコア
                   bonus_store +
                   bonus_staff)
}
```

**使用方法**:
```python
candidates_with_scores = []
for idx, csv_row in candidates_df.iterrows():
    score_result = self._calculate_score(pdf_record, csv_row, confidence, warnings)
    score_result['csv_idx'] = idx
    candidates_with_scores.append(score_result)

# スコア順ソート
candidates_with_scores.sort(key=lambda x: x['total_score'], reverse=True)
best_match = candidates_with_scores[0]
```

### 1.2 既存スコアの問題点

❌ **UI 表示に不足している情報**:
- Match rate がない（何% 一致したか不明）
- Confidence レベルがない（スコアの信頼度が不明）
- 重要項目の一致状況がない（重要項目ほど重要だが区別されていない）
- 候補間のスコア差比較がない（順位の確実性が不明）

---

## 2. Phase 4a のスコアリング設計

### 2.1 スコア計算の改良案

#### 2.1.1 基本スコア（項目別比較）

**現在の計算**:
```
base_score = match_count * 10 + diff_count * (-5) + unreadable_count * 0
            = 一致項目を+10, 不一致を-5で加点
```

**改良案: 項目の重要度を反映**:
```
base_score = Σ(各項目のスコア)

項目別スコア:
  - 重要項目 一致: +5
  - 重要項目 不一致: -10
  - 通常項目 一致: +2
  - 通常項目 不一致: -3
  - 全項目 skipped/uncertain: 0

重要項目の定義:
  - 案件系（AU, AV, DL, DM など）
  - 集計合計（AI, CZ など）
  - 主要サービス（HH, HI など）
```

#### 2.1.2 前提条件ボーナス

```
bonus_date_store = 50         # 日付+店舗コード一致（前提）
bonus_store_match = 200 * confidence  # 既存ロジック（変更なし）
```

#### 2.1.3 信頼度（Confidence）の計算

```python
if compared_fields == 0:
    confidence = 'very_low'
    confidence_multiplier = 0.3
elif compared_fields < 5:
    confidence = 'low'
    confidence_multiplier = 0.6
elif compared_fields < 15:
    confidence = 'medium'
    confidence_multiplier = 0.9
else:
    confidence = 'high'
    confidence_multiplier = 1.0

final_score = base_score * confidence_multiplier + bonus_date_store + bonus_store_match
```

#### 2.1.4 Match Rate の計算

```python
match_rate = matched_fields / compared_fields if compared_fields > 0 else 0.0

# 例：
# - 10項目中10一致 → match_rate = 100%
# - 10項目中5一致 → match_rate = 50%
# - 0項目比較可能 → match_rate = N/A
```

---

## 3. 出力形式の設計

### 3.1 複数候補のスコアリング結果

```python
candidate_scores = [
    {
        # 候補の識別情報
        'candidate_index': 0,              # candidates_df での行インデックス
        'csv_record_idx': 42,              # CSV全体での行インデックス
        
        # スコア情報
        'score': 285,                      # 総合スコア
        'base_score': 35,                  # 項目別比較スコア
        'bonus_date_store': 50,            # 日付+店舗一致ボーナス
        'bonus_store_match': 200,          # 店舗マッチボーナス
        
        # 比較結果の集計
        'compared_fields': 12,             # 比較対象項目数
        'matched_fields': 10,              # 一致項目数
        'mismatched_fields': 2,            # 不一致項目数
        'uncertain_fields': 0,             # 不確定項目数
        'skipped_fields': 171,             # スキップ項目数
        'match_rate': 0.833,               # 一致率（matched/compared）
        
        # 信頼度
        'confidence': 'high',              # very_low | low | medium | high
        'confidence_score': 1.0,           # 信頼度による乗数
        
        # 項目別詳細
        'important_items_match': 8,        # 重要項目の一致数
        'important_items_diff': 1,         # 重要項目の不一致数
        'normal_items_match': 2,           # 通常項目の一致数
        'normal_items_diff': 1,            # 通常項目の不一致数
        
        # ユーザー表示用
        'score_rank': 1,                   # 複数候補内での順位（1位が最高）
        'score_gap_to_next': 45,           # 次点との点数差
        'recommendation': 'best_match',    # best_match | recommended | ambiguous | low_confidence
        'reasons': [                       # スコア根拠
            'High match rate (83.3%)',
            '8/9 important items matched',
            'Confident field comparison (12 items)'
        ]
    },
    {
        'candidate_index': 1,
        'score': 240,
        'match_rate': 0.667,
        'confidence': 'medium',
        'score_rank': 2,
        'score_gap_to_next': 45,
        'recommendation': 'recommended',
        'reasons': [
            'Moderate match rate (66.7%)',
            '6/9 important items matched'
        ]
    }
]
```

### 3.2 複数候補の最終結果

```python
# reconcile_pdf_with_csv() の返り値に追加

return {
    # ... 既存項目 ...
    'status': 'review',  # 複数候補なので必ず review
    
    # Phase 4a スコアリング結果
    'candidate_scores': [
        { ... },  # 上記の形式
        { ... }
    ],
    'best_match_index': 0,               # 最高スコアの候補インデックス
    'score_decision_confidence': 'high',  # スコア判定の信頼度
                                         # high: 1位が圧倒的
                                         # medium: スコア差がある程度
                                         # low: スコア同点や接近
    'recommendation': 'best_match',      # UI 表示用推奨候補
}
```

---

## 4. 自動確定しない条件の定義

### 4.1 複数候補時の判定ロジック

```python
# Phase 3 ステータスは必ず review（変更なし）
if match_status == 'multiple_csv_candidates':
    final_status = 'review'  # 常に review
    return final_status

# Phase 4a: UI 用推奨候補の提示（自動確定しない）
if len(candidate_scores) > 1:
    
    # ケース1: 1位が圧倒的（スコア差 > 100）
    if candidate_scores[0]['score'] - candidate_scores[1]['score'] > 100:
        score_decision_confidence = 'high'
        recommendation = 'best_match'
        note = 'Best match is significantly ahead'
    
    # ケース2: スコア差がある程度（50 < diff ≤ 100）
    elif candidate_scores[0]['score'] - candidate_scores[1]['score'] > 50:
        score_decision_confidence = 'medium'
        recommendation = 'recommended'
        note = 'Recommended but manual confirmation recommended'
    
    # ケース3: スコア同点か僅差（diff ≤ 50）
    else:
        score_decision_confidence = 'low'
        recommendation = 'ambiguous'
        note = 'Candidates are similar, manual selection required'
    
    # ケース4: 比較対象が少ない
    if candidate_scores[0]['compared_fields'] < 5:
        score_decision_confidence = 'very_low'
        recommendation = 'low_confidence'
        note = 'Too few comparable fields, low confidence in scores'
```

### 4.2 自動確定の条件（参考）

**Phase 4a では自動確定しないが、将来参考用**:

```python
# 自動確定候補（Phase 4b 以降で検討）
# - スコア差 > 150 かつ matched_fields > 15
# - confidence == 'high' かつ match_rate > 90%
# - 重要項目で全一致（important_items_diff == 0）
```

---

## 5. テスト方針

### 5.1 最小テストケース

#### グループ1: スコア計算の正確性（4件）

1. **test_scoring_matched_items_score_correctly**
   - 10項目中10一致 → base_score = 10 * (+2) = 20
   - match_rate = 100%

2. **test_scoring_mismatched_items_score_correctly**
   - 10項目中2不一致 → base_score = 8 * (+2) + 2 * (-3) = 16 - 6 = 10
   - match_rate = 80%

3. **test_scoring_important_items_bonus**
   - 重要項目5個中5一致 → base_score = 5 * (+5) = 25
   - 通常項目5個中3一致 → base_score += 3 * (+2) = 6
   - 合計: 31

4. **test_scoring_skipped_items_ignored**
   - 20項目中：10一致, 2不一致, 8スキップ
   - base_score = 10 * (+2) + 2 * (-3) = 14
   - compared_fields = 12（スキップは含めない）

#### グループ2: 信頼度の計算（3件）

5. **test_confidence_very_low_zero_compared_fields**
   - compared_fields = 0 → confidence = 'very_low'
   - confidence_multiplier = 0.3
   - final_score = base_score * 0.3 + bonuses

6. **test_confidence_medium_moderate_compared_fields**
   - compared_fields = 10 → confidence = 'medium'
   - confidence_multiplier = 0.9

7. **test_confidence_high_many_compared_fields**
   - compared_fields = 20 → confidence = 'high'
   - confidence_multiplier = 1.0

#### グループ3: 複数候補の順位付け（4件）

8. **test_candidate_scoring_clear_winner**
   - 候補1: score = 300, 候補2: score = 150
   - score_gap_to_next = 150 > 100
   - recommendation = 'best_match', confidence = 'high'

9. **test_candidate_scoring_moderate_difference**
   - 候補1: score = 250, 候補2: score = 180
   - score_gap_to_next = 70（50 < 70 ≤ 100）
   - recommendation = 'recommended', confidence = 'medium'

10. **test_candidate_scoring_ambiguous**
    - 候補1: score = 200, 候補2: score = 190
    - score_gap_to_next = 10 ≤ 50
    - recommendation = 'ambiguous', confidence = 'low'

11. **test_candidate_scoring_low_confidence_few_fields**
    - 候補1: score = 250（high actual score）
    - compared_fields = 2 < 5
    - recommendation = 'low_confidence'（スコア差優先度より信頼度優先）

#### グループ4: 単一候補の場合（1件）

12. **test_single_candidate_uses_phase3_logic**
    - match_status = 'candidate_found'
    - Phase 4a スコアリングは実行されない
    - Phase 3 の判定結果（match/mismatch/review）をそのまま使用

### 5.2 テストデータの構造

```python
# ダミー候補スコアデータ
sample_scores = [
    {
        'candidate_index': 0,
        'score': 285,
        'compared_fields': 12,
        'matched_fields': 10,
        'mismatched_fields': 2,
        'match_rate': 0.833,
        'confidence': 'high',
        'important_items_match': 8,
        'important_items_diff': 1,
    },
    {
        'candidate_index': 1,
        'score': 240,
        'compared_fields': 12,
        'matched_fields': 8,
        'mismatched_fields': 4,
        'match_rate': 0.667,
        'confidence': 'medium',
        'important_items_match': 6,
        'important_items_diff': 2,
    }
]
```

---

## 6. 変更対象ファイル候補

### 6.1 必須変更（Phase 4a）

| ファイル | 変更内容 | 説明 |
|---------|---------|------|
| **reconciliation_phase1.py** | `_score_candidate_by_fields()` 新規 | 項目別スコア計算（重要度反映） |
| | `_calculate_confidence()` 新規 | Confidence レベル計算 |
| | `_calculate_match_rate()` 新規 | Match rate 計算 |
| | `_rank_candidates()` 新規 | 複数候補の順位付け |
| | `reconcile_pdf_with_csv()` 拡張 | candidate_scores, recommendation 追加 |
| **tests/test_phase4a_candidate_scoring.py** | 新規作成 | スコアリングロジックのテスト |

### 6.2 参照のみ（変更なし）

| ファイル | 参照方法 |
|---------|--------|
| **reconciliation_phase1.py** | 既存の _calculate_score() は互換性維持 |
| **phase3_field_comparison.py** | Phase 3 判定ロジックはそのまま |

### 6.3 後続フェーズで検討

| ファイル | 検討事項 | 時期 |
|---------|--------|------|
| **app.py** | 複数候補の UI 表示（候補リスト、スコア表示） | Phase 4b+ |
| **reconciliation.py** | 複数候補時のワークフロー（確認画面など） | Phase 4b+ |

---

## 7. 実装時の注意点

### 7.1 重要項目の定義

**懸念**: 重要項目の定義が恣意的になる可能性

```python
IMPORTANT_ITEMS = {
    'AU', 'DL', 'AV', 'DM',  # 案件
    'AI', 'CZ',               # 合計
    'HH', 'HI', 'HJ', 'IG', 'IH',  # 主要サービス
}

# または pdf_csv_field_mapping.csv に importance フラグを追加
```

**対応**: Phase 4a では固定リストで開始し、Phase 4b で csv マスタから読むように変更

### 7.2 スコア計算の安定性

**懸念**: スコア絶対値がページごと・時間ごとに変動する可能性

```python
# 例: compared_fields が増えるとスコアの意味が変わる
# - 少数フィールド: 1項目の重み大 (score = 50)
# - 多数フィールド: 1項目の重み小 (score = 5)
```

**対応**: 
- Confidence 乗数で正規化
- Match rate（相対値）を優先表示
- スコア差よりは confidence を重視

### 7.3 候補の tie-breaking（同点対応）

**懸念**: スコアが完全に同じ候補が複数出た場合

```python
# Tie-breaking 優先度
1. Match rate (高い方)
2. Important items match count (多い方)
3. CSV行インデックス (若い方 = 古い方)
```

### 7.4 Confidence と自動確定の分離

**懸念**: confidence が high でも自動確定してしまう

```python
# 重要: Phase 4a では自動確定しない
# recommendation != 'auto_confirm'
# 常に review ステータスで人間判定に委ねる
```

### 7.5 Phase 3 との整合性

**懸念**: 複数候補時に Phase 3 結果が無視されてしまう

```python
# Phase 4a の recommendation は UI 提示用
# 最終的な final_status = review は変わらない
# Phase 3 の field_comparison 結果は保持される
```

---

## 8. 実装の段階

### Stage 1: スコア計算の改良

```
_score_candidate_by_fields()
├─ 項目の重要度判定
├─ 重要度別スコア計算
└─ base_score 出力
```

### Stage 2: Confidence & Match Rate

```
_calculate_confidence()
├─ compared_fields 数から confidence を決定
└─ confidence_multiplier を返す

_calculate_match_rate()
├─ matched_fields / compared_fields
└─ match_rate（0-1）を返す
```

### Stage 3: 候補の順位付け

```
_rank_candidates()
├─ 全候補をスコアでソート
├─ スコア差を計算
├─ recommendation を決定
└─ candidate_scores を返す
```

### Stage 4: 統合

```
reconcile_pdf_with_csv()
├─ 複数候補の場合、_rank_candidates() を呼び出し
├─ candidate_scores を結果に追加
└─ status = 'review' で返す（変更なし）
```

### Stage 5: テスト

```
test_phase4a_candidate_scoring.py
└─ 12テストケース all pass
```

---

## 9. リスク & 対応

| リスク | 影響 | 対応 |
|--------|------|------|
| スコアが負になる | UI 表示破損 | min_score = 0 制限 |
| 重要項目定義が不正確 | 候補順位が誤る | CSV マスタから読み込み化 |
| confidence の計算誤り | 信頼度不正確 | テストで各レンジを検証 |
| Phase 3 との二重判定 | ユーザー混乱 | status = review は変更なし |
| 候補が1件の場合のオーバーヘッド | 処理遅延 | Early return で最小化 |

---

## 10. マイルストーン

| 対象 | 進捗 |
|------|------|
| **Phase 1** | ✅ 完了（shop_code 変換） |
| **Phase 2** | ✅ 完了（日付+店舗検索） |
| **Phase 3** | ✅ 完了（フィールド比較） |
| **Phase 4a** | 📋 計画中（候補スコアリング） |
| **Phase 4b** | ⏳ 検討中（UI実装） |
| **Phase 5** | ⏳ 検討中（確認ワークフロー） |

---

**計画書作成日**: 2026-06-05  
**版**: 1.0 (設計段階)  
**ステータス**: 実装前レビュー待ち


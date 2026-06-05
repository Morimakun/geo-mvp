# Phase 4b 実装計画：照合結果確認UI

## 概要

Phase 1〜4a の照合結果を、事務局担当者が確認・検証しやすい画面に表示する設計。

**目的**: 複数候補やフィールド不一致を可視化し、事務局の確認作業を支援  
**対象**: app.py の結果表示セクション  
**スコープ**: UI表示のみ（データ保存・確定ボタンは Phase 5 以降）

---

## 1. app.py 現在の構成確認

### 1.1 既存の構造

**ファイル**: `app.py`

**主要フロー**:
```
Tab 1: PDF一括アップロード
├─ ファイル入力
│  ├─ Salesforce CSV アップロード
│  ├─ PDF複数ファイル アップロード
│  └─ 対象営業日指定
├─ 照合実行
│  └─ reconciliation_phase1.py を呼び出し
└─ 結果表示（現在は基本情報のみ）

Tab 2: CSVデモモード
└─ サンプルデータでの動作確認
```

### 1.2 既存の結果表示

**現状の出力フォーマット**:
- `reconciliation_phase1.reconcile_pdf_with_csv()` の返り値
  - Phase 1-3 の基本情報
  - Phase 4a の candidate_scores（複数候補時のみ）

**現在の表示内容**（推定）:
- ステータス（match/mismatch/review）
- スコア情報（古いアルゴリズムベース）
- マッチした項目/不一致項目のリスト

---

## 2. Phase 4b UI設計

### 2.1 全体構成

```
照合結果確認画面（新Tab または 既存Tab拡張）
├─ [1] 一覧表示
│  └─ ページ単位のサマリーテーブル
├─ [2] 詳細表示（詳細ボタン押下時）
│  ├─ 基本情報セクション
│  ├─ 複数候補セクション（複数候補時のみ）
│  └─ フィールド比較詳細
└─ [3] ダウンロード
   └─ 確認用CSV生成
```

---

## 3. [1] 一覧表示（ページサマリー）

### 3.1 テーブル設計

**表示形式**: Streamlit DataFrame（ソート・検索可能）

**カラム構成**:

| 列 | データ型 | 説明 | 例 |
|---|---------|------|-----|
| **Page** | int | ページ番号 | 1, 2, 3 |
| **Date** | str | PDF 営業日 | 2026/05/17 |
| **Store** | str | 店舗名（PDF読取） | 小倉 |
| **Code** | str | 取扱店コード | AU1K0024112 |
| **Status** | str | 最終ステータス（色分け） | ✅ match |
| **Match Type** | str | CSV候補状況 | 1候補 / 複数候補 |
| **Candidates** | int | CSV候補数 | 1, 2, 3 |
| **Match Rate** | str | フィールド一致率 | 83% |
| **Confidence** | str | スコア信頼度（色分け） | high |
| **Recommendation** | str | 推奨候補（複数時） | best_match |
| **Issues** | str | 要確認事項 | 2 mismatch |
| **Action** | button | 詳細表示 | [詳細] |

### 3.2 ステータス色分け

```python
status_colors = {
    'match': ('✅ match', 'green'),
    'mismatch': ('❌ mismatch', 'red'),
    'review': ('⚠️ review', 'orange'),
}

confidence_colors = {
    'very_low': ('very_low', '#ff6b6b'),
    'low': ('#ffb700'),
    'medium': ('#ffd700'),
    'high': ('#38a169'),
}
```

### 3.3 フィルター機能（初期版は最小限）

```
フィルター条件:
- Status で絞込（match / mismatch / review）
- Confidence で絞込（high / medium / low / very_low）
```

---

## 4. [2] 詳細表示

### 4.1 基本情報セクション

**レイアウト**: 2列グリッド

```
─────────────────────────────
│ PDF情報            │ CSV照合結果
├─────────────────────────────
│ ページ: 1          │ ステータス: review
│ 営業日: 2026/05/17 │ CSV候補: 複数候補（2件）
│ 店舗名: 小倉        │ 最高スコア: 285
│ 取扱コード: AU1K... │ Match Rate: 83.3%
│ 読取者: スタッフA   │ Confidence: high
│                    │ Recommendation: best_match
└─────────────────────────────
```

### 4.2 複数候補セクション（複数候補時のみ表示）

**表示形式**: タブ または 折りたたみ式

```
複数CSV候補（2件）
┌─────────────────────────────────┐
│ タブ: [候補1: 285pt] [候補2: 135pt]│
├─────────────────────────────────┤
│ 候補1 詳細                        │
│ ┌───────────────────────────────┐│
│ │ Rank: 1位                      ││
│ │ Score: 285pt                   ││
│ │ Match Rate: 83.3%              ││
│ │ Confidence: high               ││
│ │ Important Items Matched: 8/9   ││
│ │ Recommendation: best_match     ││
│ │                                ││
│ │ CSV Row Preview:               ││
│ │ ├─ 営業日: 2026/05/17         ││
│ │ ├─ 取扱コード: AU1K0024112    ││
│ │ ├─ col1: 100                   ││
│ │ ├─ col2: 50                    ││
│ │ └─ ...                         ││
│ └───────────────────────────────┘│
│ 候補2 詳細                        │
│ ┌───────────────────────────────┐│
│ │ Rank: 2位                      ││
│ │ Score: 135pt                   ││
│ │ Match Rate: 66.7%              ││
│ │ Confidence: medium             ││
│ │ Important Items Matched: 6/9   ││
│ │ Recommendation: ambiguous      ││
│ └───────────────────────────────┘│
└─────────────────────────────────┘
```

### 4.3 フィールド比較詳細セクション

**表示形式**: 折りたたみ式または スクロールテーブル

```
フィールド比較詳細（12/15 比較対象）
┌────────────────────────────────────────────┐
│ 検索/フィルター: [テキスト入力]              │
│ フィルター: [全て] [一致] [不一致] [スキップ] │
├────────────────────────────────────────────┤
│テーブル:
│
│ Item | Column | PDF値 | CSV値 | Status | Reason
│──────┼────────┼──────┼──────┼────────┼──────────
│ AU  │ AU    │ 5    │ 5    │ ✅ match│
│ DL  │ DL    │ 3    │ 4    │ ❌ mismatch│ 値が異なる
│ AV  │ AV    │ 2    │ 2    │ ✅ match│
│ AI  │ AI    │ 80   │ 80   │ ✅ match│
│ CZ  │ CZ    │ 120  │ 120  │ ✅ match│
│ HH  │ HH    │ 15   │ 15   │ ✅ match│
│ HI  │ HI    │ 25   │ 25   │ ✅ match│
│ HJ  │ HJ    │ null │ -    │ ⏭️ skipped│ PDF値なし
│ IG  │ IG    │ uncertain│ 10│⏭️ skipped│ PDF不確定
│ IH  │ IH    │ 50   │ 50   │ ✅ match│
│ X1  │ X1    │ 30   │ 30   │ ✅ match│
│ X2  │ X2    │ 40   │ 40   │ ✅ match│
│
└────────────────────────────────────────────┘

凡例:
✅ match     — 値が一致
❌ mismatch  — 値が異なる
⏭️ skipped   — 比較対象外（理由：PDF値なし/不確定/CSV値なし）
```

**テーブルカラム**:

| 列 | データ型 | 説明 |
|----|---------|------|
| Item | str | FAX項目名 |
| Column | str | CSV列コード |
| CSV Column Name | str | CSV列の完全名称 |
| PDF Value | str/int | PDF読取値 |
| CSV Value | str/int | CSV値 |
| Status | str | match / mismatch / skipped_* |
| Reason | str | 理由（不一致の場合） |

---

## 5. [3] ダウンロード機能

### 5.1 確認用CSV生成

**ファイル名**: `reconciliation_result_{datetime}.csv`

**出力形式**: UTF-8 with BOM

**カラム構成** (ページサマリー行):

```csv
page_number,pdf_date,pdf_store_name,mapped_store_code,csv_candidate_count,match_status,final_status,match_rate,compared_fields,matched_fields,mismatched_fields,skipped_fields,confidence,recommendation,review_reasons
1,2026/05/17,小倉,AU1K0024112,1,candidate_found,mismatch,83.3%,12,10,2,171,high,best_match,2 mismatched fields
2,2026/05/17,小倉,AU1K0024112,1,candidate_found,mismatch,83.3%,12,10,2,171,high,best_match,2 mismatched fields
```

### 5.2 複数候補の場合の追加シート（オプション）

```
candidate_details シート:

page_number,candidate_rank,candidate_index,score,match_rate,matched_fields,mismatched_fields,skipped_fields,confidence,recommendation
1,1,0,285,83.3%,10,2,171,high,best_match
1,2,1,135,66.7%,8,4,171,medium,ambiguous
```

---

## 6. UI操作フロー

### 6.1 ユーザーシナリオ1: 単一候補（match）

```
1. [一覧] ページ1, 店舗=小倉, Status=match を確認
2. [詳細] ボタンを押す
3. 基本情報を確認
4. フィールド比較詳細を確認
5. [ダウンロード] で CSV 出力
```

### 6.2 ユーザーシナリオ2: 複数候補（review）

```
1. [一覧] ページ3, 店舗=梅田, Status=review, Candidates=2 を確認
2. [詳細] ボタンを押す
3. 基本情報を確認
4. 「複数CSV候補」セクションで
   - 候補1（スコア150）: best_match
   - 候補2（スコア120）: ambiguous
   を比較
5. フィールド比較詳細で両候補を確認
6. [ダウンロード] で CSV 出力（事務局がOfficeで確認）
```

### 6.3 ユーザーシナリオ3: 不一致確認（mismatch）

```
1. [一覧] ページ5, 店舗=京都, Status=mismatch を確認
2. [詳細] ボタンを押す
3. フィールド比較詳細で不一致項目を確認
   - DL: PDF=4, CSV=5（❌ mismatch）
   - HI: PDF=null, CSV=10（⏭️ skipped）
4. 理由を確認し、手動修正 or 次ページへ
```

---

## 7. 技術実装設計

### 7.1 新規Componentの作成案

```python
# helpers/result_display.py （新規作成）

def format_page_summary_table(results: List[Dict]) -> pd.DataFrame:
    """Phase 1-4a の結果から一覧テーブル用 DataFrame を生成"""
    pass

def render_detail_view(result: Dict, candidate_scores: List[Dict]):
    """詳細ビューを Streamlit で描画"""
    pass

def render_field_comparison_table(field_comparisons: List[Dict]) -> None:
    """フィールド比較テーブルを描画"""
    pass

def generate_download_csv(results: List[Dict]) -> Tuple[bytes, str]:
    """ダウンロード用 CSV を生成"""
    pass
```

### 7.2 app.py への修正

**新規セクション追加**:

```python
# Tab または 新Tab: "📊 照合結果確認"
with tab_results:  # または既存 tab に追加
    # [1] 一覧表示
    st.markdown("## ページサマリー")
    summary_df = format_page_summary_table(st.session_state.reconciliation_results)
    st.dataframe(summary_df, use_container_width=True)
    
    # [2] 詳細表示（詳細ボタンから遷移）
    selected_page = st.selectbox("詳細を表示するページを選択", options=...)
    if selected_page:
        render_detail_view(result, candidate_scores)
    
    # [3] ダウンロード
    if st.button("確認用CSV をダウンロード"):
        csv_bytes, filename = generate_download_csv(...)
        st.download_button(...)
```

---

## 8. 変更対象ファイル候補

### 必須変更

| ファイル | 変更内容 | 理由 |
|---------|---------|------|
| **app.py** | 結果表示セクション追加 | Phase 4a 結果を表示 |
| **helpers/result_display.py** (新規) | 表示用Helper関数 | 表示ロジック分離 |

### 原則触らない

| ファイル | 理由 |
|---------|------|
| **reconciliation_phase1.py** | 照合ロジックは不変 |
| **extractor.py** | PDF抽出は不変 |
| **reconciliation.py** | 既存照合ロジックは不変 |

---

## 9. テスト方針（初期版）

### 最小テストケース

```python
# tests/test_phase4b_ui_helpers.py （新規作成）

def test_format_page_summary_table():
    """一覧テーブルのフォーマット"""
    pass

def test_render_field_comparison_table():
    """フィールド比較テーブルの描画"""
    pass

def test_generate_download_csv():
    """ダウンロードCSVの生成"""
    pass
```

### テスト対象

- ✅ Helper関数（DataFrame生成、フォーマット）
- ✅ CSV生成ロジック
- ⚠️ Streamlit描画は手動確認（st.write 等は automated test困難）

### テスト非対象（Phase 5以降）

- 事務局による確定ボタン操作
- DB保存ロジック
- メール通知ロジック

---

## 10. 実装時の注意点

### セキュリティ

```python
# ❌ 禁止：
# - Salesforce CSVの生データをUI上に表示
# - 個人情報（スタッフ名など）をCSV出力に含める

# ✅ 推奨：
# - 表示/出力時は必要最小限の情報に絞る
# - ログには記録するが、画面には表示しない
```

### パフォーマンス

```python
# 多数ページの場合の対応:
# - 一覧テーブルはページネーション（初期版は不要、Phase 5で検討）
# - 詳細ビューは遅延描画（詳細ボタン押下時のみ）
```

### UI/UX

```python
# ✅ 推奨設計：
# - ステータス・信頼度は色分け（視認性向上）
# - 不一致項目は目立つ色で強調
# - モバイル対応は不要（事務局PCでの利用想定）
```

---

## 11. 段階的実装計画

### Phase 4b（現在）

```
Stage 1: Helper関数の実装
├─ format_page_summary_table()
├─ render_detail_view()
├─ render_field_comparison_table()
└─ generate_download_csv()

Stage 2: app.py への統合
├─ 新Tab または 既存Tab拡張
├─ 一覧表示の実装
├─ 詳細表示の実装
└─ ダウンロード機能の実装

Stage 3: テスト・調整
├─ Helper テスト
├─ UI レイアウト調整
└─ 日本語表示の確認
```

### Phase 5（次フェーズ）

```
- 確定ボタン追加
- DB保存ロジック
- メール通知
- ページネーション
```

---

## 12. リスク & 対応

| リスク | 影響 | 対応 |
|--------|------|------|
| Streamlit レイアウトの複雑化 | UI表示破損 | 早期に動作確認 |
| CSV生成エラー | ダウンロード失敗 | try-catch で例外処理 |
| 大規模データ対応 | 処理遅延 | Phase 5でページネーション追加 |
| 事務局の確認作業が増加 | 作業効率低下 | UI改善フィードバック収集 |

---

## 13. マイルストーン

| 対象 | 進捗 |
|------|------|
| **Phase 1** | ✅ 完了 |
| **Phase 2** | ✅ 完了 |
| **Phase 3** | ✅ 完了 |
| **Phase 4a** | ✅ 完了 |
| **Phase 4b** | 📋 計画中（設計段階） |
| **Phase 5** | ⏳ 検討中（確定・保存機能） |

---

**計画書作成日**: 2026-06-05  
**版**: 1.0 (設計段階)  
**ステータス**: 実装前設計完了


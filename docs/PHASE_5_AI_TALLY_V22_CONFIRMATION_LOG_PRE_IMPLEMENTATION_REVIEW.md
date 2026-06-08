# Phase 5 AI Tally V2.2 Confirmation Log - Pre-Implementation Review

**レビュー日:** 2026-06-08  
**対象:** Phase 5 Step 5 確認ログ設計書・サンプルCSV  
**目的:** Step 6 アプリ実装に進んでよいか判断する  

---

## レビュー概要

このドキュメントは、確認ログ設計書（Phase 5 Step 5の成果物）と、サンプルCSVの整合性・妥当性をレビューしたものです。

**実装は行いません。**

**目的は、以下を固定すること：**

- user_action の正本
- user_decision の正本
- status（before/after）の正本
- P14/P16/P30 の代表ケースの扱い
- Step 6 で安全に実装に進められるか判断

---

## 確認したファイル

- docs/PHASE_5_AI_TALLY_V22_CONFIRMATION_LOG_DESIGN.md
- data/test_outputs/phase5_ai_tally_v22_confirmation_log_sample.csv
- scripts/ai_tally_v22.py
- tests/test_ai_tally_v22.py
- app.py （未編集確認）

---

## 現在のログ設計概要

### 基本方針

- **ログ対象イベント数:** 12個
- **ログ項目数:** 27項目
- **エンコーディング:** UTF-8 with BOM
- **用途:** 人間の確認行動記録・監査証跡

### ステータス遷移

\\\
unreviewed
  ↓
[auto_confirm_candidate 候補] OR [review_required 要確認]
  ↓
  ├→ confirmed （確認済み）
  ├→ corrected （修正済み）
  ├→ deferred （保留中）
  └→ skipped （スキップ）
\\\

重要：auto_confirm_candidate は「候補」であり「確定済み」ではない。

---

## CSVサンプル確認結果

### 検証結果

| 項目 | 結果 |
|-----|------|
| ファイル読み込み | OK |
| 行数 | 6行（ヘッダー除く）|
| 列数 | 27列 |
| user_action の定義済み値チェック | OK |
| user_decision の定義済み値チェック | OK |
| before_status の定義済み値チェック | OK |
| after_status の定義済み値チェック | OK |
| P14 ケース確認 | OK |
| P16 ケース確認 | OK |
| P30 ケース確認 | OK |
| download_csv イベント | OK |
| view イベント | OK |

### サンプルCSV内容

**6行の内訳：**

1. P14 (auto_confirm_candidate 確認) → confirmed
2. P16 (review_required 保留) → deferred
3. P30 (auto_confirm_candidate 修正) → corrected
4. download_csv イベント (ページなし)
5. view イベント (ページなし)
6. P16 (review_required 修正確定) → corrected

---

## user_action 正本確定

以下の11個に統一します。**これがStep 6での正本です。**

\\\
view
download_csv
confirm
correct
select_csv
select_pdf
select_v3
select_v22
defer
skip
override_classification
\\\

### 対応する設計書の「ログ対象イベント」

| user_action | ログイベント名 | 説明 |
|-----------|-----------|------|
| view | v22_section_viewed | V2.2セクション表示 |
| download_csv | v22_csv_downloaded | CSV ダウンロード |
| confirm | auto_candidate_confirmed<br/>review_item_confirmed | 確認・承認 |
| correct | manual_value_corrected | 値を修正 |
| select_csv | csv_value_selected_as_final | CSV値を採用 |
| select_pdf | pdf_value_selected_as_final | PDF値を採用 |
| select_v3 | v3_value_selected_as_final | v3値を採用 |
| select_v22 | v22_value_selected_as_final | v22値を採用 |
| defer | decision_deferred | 判定を保留 |
| skip | item_skipped | スキップ |
| override_classification | classification_overridden | 分類上書き |

**注意:** ログ対象イベント名と user_action は役割を分ける。
- イベント名：何が起きたか（ビジネスロジック）
- user_action：ユーザーが何をしたか（UI操作）

---

## user_decision 正本確定

以下の8個に統一します。**これがStep 6での正本です。**

\\\
accept_v22        # V2.2の値を採用
accept_csv        # CSVの値を採用
accept_pdf        # PDF値を採用
accept_v3         # v3の値を採用
manual_correct    # 手動修正（manual_correction_value に値）
defer             # 判定を保留
skip              # スキップ
needs_follow_up   # 追加確認が必要
\\\

（view, download_csv イベントでは user_decision は空）

---

## status 正本確定

### before_status / after_status の候補

\\\
unreviewed           # 初期状態（未確認）
auto_confirm_candidate # V2.2が「確定候補」と判定
review_required      # V2.2が「要確認」と判定
confirmed            # 人間が確認・承認した
corrected            # 人間が値を修正した
deferred             # 判定を保留した
skipped              # スキップした
\\\

**注意:** pending ではなく deferred を使用。

### ステータス遷移例

\\\
unreviewed → auto_confirm_candidate → confirmed
unreviewed → auto_confirm_candidate → corrected
unreviewed → auto_confirm_candidate → deferred
unreviewed → review_required → confirmed
unreviewed → review_required → corrected
unreviewed → review_required → deferred
\\\

---

## P14 の扱い

**分類:** auto_confirm_candidate（自動確定候補）

| 項目 | 値 |
|-----|-----|
| page | 14 |
| v3_value | 34 |
| v22_value | 3 |
| csv_value | 3 |
| confidence | high |
| classification | auto_confirm_candidate |
| user_action | confirm |
| user_decision | accept_v22 |
| before_status | auto_confirm_candidate |
| after_status | confirmed |

**評価:** 妥当

**理由:** 
- v3=34はOCR誤読（手書き「3」を「34」と誤認）
- V2.2が正しく3を推定
- CSVと一致
- 人間が confirm で承認

**Step 6への影響:** ボタン「確認済み」のシンプルなケースとして採用可。

---

## P16 の扱い

**分類:** review_required（要確認）

| 項目 | P16-1（保留） | P16-2（修正確定） |
|-----|----------|----------|
| page | 16 | 16 |
| v3_value | 9 | 9 |
| v22_value | 2 | 2 |
| csv_value | 11 | 11 |
| confidence | low | low |
| classification | review_required | review_required |
| user_action | defer | correct |
| user_decision | needs_follow_up | manual_correct |
| manual_correction_value | (empty) | 11 |
| before_status | review_required | deferred |
| after_status | deferred | corrected |

**評価:** 妥当

**重要なポイント：**

1. P16は auto_confirm_candidate ではない
2. confidence=low のため review_required に分類された
3. ユーザーの流れ：
   - 一度保留（needs_follow_up：店舗確認待ち）
   - 後から確認して修正（CSV=11が正しい）
4. confirmed ではなく corrected（修正値を入力）
5. 修正前後の値を記録：
   - 修正前：v3, v22, csv から判定
   - 修正後：manual_correction_value=11

**Step 6への影響:** ボタンは「修正」「保留」「確認」の3種類が必要。この流れをシミュレートできる教科書的ケース。

---

## P30 の扱い

**分類:** auto_confirm_candidate + 手動修正

| 項目 | 値 |
|-----|-----|
| page | 30 |
| v3_value | 2 |
| v22_value | 1 |
| csv_value | 1 |
| confidence | high |
| classification | auto_confirm_candidate |
| user_action | correct |
| user_decision | manual_correct |
| manual_correction_value | 0 |
| final_value | 0 |
| before_status | auto_confirm_candidate |
| after_status | corrected |
| decision_reason | PDFを詳細確認したら0が正しい。手書きが薄い。 |

**判定:** 案B（手動修正例として残す）を採用

**理由：**

1. **実際の運用シナリオ:** V2.2とCSVが一致していても、人間がPDFを再確認したら「実際は別の値」と判定することはあり得る
2. **監査証跡として重要:** 「なぜ自動推定と異なる値にしたのか」という判定がログに残る
3. **Step 6のボタンテスト:** 「修正」ボタンの動作確認に適している
4. **デモ時の説明:** decision_reason があるため「人間が確認した」という説明が可能

**decision_reason が記載されているため、デモ時の説明も容易。**

---

## download_csv / view の扱い

### download_csv イベント

| 項目 | 値 |
|-----|-----|
| user_action | download_csv |
| user_decision | (empty) |
| page | (empty) |
| before_status | (empty) |
| after_status | (empty) |

**評価:** 妥当

**説明:** ページ単位でなく、全体的なCSVダウンロード操作なため、ページ情報なし。

### view イベント

| 項目 | 値 |
|-----|-----|
| user_action | view |
| user_decision | (empty) |
| page | (empty) |
| before_status | (empty) |
| after_status | (empty) |

**評価:** 妥当

**説明:** V2.2セクションを表示したことを記録。ステータス変更ではないため after_status は空。

---

## Step 6 で実装する範囲

**app.py に追加予定：**

1. ボタングループ
   - 「確認済み」（user_action=confirm）
   - 「修正」（user_action=correct）
   - 「保留」（user_action=defer）
   - 「スキップ」（user_action=skip）
   - 「分類上書き」（user_action=override_classification）

2. 各ボタン押下時の処理
   - log_id と timestamp を自動生成
   - st.session_state.confirmation_logs に append
   - 必要に応じて user_decision / manual_correction_value を入力

3. セッション終了時のCSV出力
   - ファイル名：phase5_ai_tally_v22_confirmation_log_YYYYMMDD_HHMM.csv
   - エンコーディング：UTF-8 with BOM
   - 場所：data/logs/ 配下（新規作成）

---

## Step 6 で実装しない範囲

❌ DB (SQLite, PostgreSQL) 連携  
❌ Salesforce 自動更新  
❌ ログの集計ダッシュボード  
❌ 暗号化・アクセス制御  
❌ ユーザー認証（既存の app.py に委譲）  

これらは Phase 5 Step 7 以降で段階実装。

---

## 未追跡ファイルの確認結果

git status で報告されている未追跡ファイルを確認しました。

### Phase 6B の中間ファイル（削除推奨の候補）

以下のファイル/フォルダは Phase 6B の Vision API テスト・クロップ生成時の中間ファイルです。

**ファイル:**
- data/test_outputs/P14_CROP_GENERATION_REPORT.md
- data/test_outputs/phase6b_ai_tally_prompt_v21_context_actual_result.csv
- data/test_outputs/phase6b_ai_tally_prompt_v21_context_raw_responses.json
- data/test_outputs/phase6b_ai_tally_prompt_v21_highres_crop_status.csv
- data/test_outputs/phase6b_ai_tally_prompt_v2_actual_result.csv
- docs/P14_CROP_GENERATION_STATUS.md
- docs/P14_CROP_VISUAL_GUIDE.md
- docs/PHASE_6B_AI_TALLY_PROMPT_V21_CONTEXT_ACTUAL_RESULT.md
- docs/PHASE_6B_AI_TALLY_PROMPT_V21_HIGHRES_STATUS.md
- run_vision_test.py
- scripts/*.py（run_v21_test.py など）
- scripts/run_v22_test_secure.ps1

**フォルダ:**
- data/test_outputs/p14_position_audit_crops/
- data/test_outputs/phase6b_ai_tally_v21_crops/
- data/test_outputs/phase6b_ai_tally_v22_expansion_crops/

### 推奨される処理

**今回は削除しません（指示書より）。**

将来的な処理案：

1. **別ブランチで管理:** Phase 6B 専用ブランチに移動
2. **.gitignore に追加:** 自動生成ファイルなので無視対象にしてもOK
3. **手動クリーンアップ:** Step 6 実装完了後に別途整理

**Step 6 実装には影響なし。**

---

## リスク評価

### 低リスク

- user_action / user_decision / status の定義が明確で、CSVと整合している
- P14/P16/P30 のケースはいずれも代表的で妥当
- py_compile と pytest が PASS

### 中リスク

- P30 の「自動候補なのに手動修正」は、デモ時に「なぜ修正したのか」と質問される可能性
  - **対策:** decision_reason が記載されているため説明可能

### 対応済み

- app.py は編集されていない（確認済み）
- Vision API は再実行されていない（確認済み）
- V2.2 分類ロジックは変更されていない（確認済み）

---

## 結論

### **✓ Step 6 実装に進んでよい**

以下の理由：

1. **設計書とCSVの整合性が確認できた**
   - user_action, user_decision, status がすべて一致
   - 27項目すべてが揃っている

2. **user_action / user_decision / status の正本が固定できた**
   - Step 6 では混在なく一貫して使用可能

3. **P14/P16/P30 の代表ケースが妥当**
   - P14：auto_confirm_candidate → confirmed（シンプルケース）
   - P16：review_required → deferred → corrected（複雑な流れ）
   - P30：auto_confirm_candidate + 手動修正（判定上書きケース）
   - デモ・テストに使用可能

4. **既存コードへの影響なし**
   - app.py 未編集
   - Vision API 未実行
   - ai_tally_v22.py 分類ロジック変更なし

5. **pytest 41/41 PASS**
   - 既存機能は維持

### Next Step

Phase 5 Step 6：確認ログボタン実装
- app.py の [4] セクションにボタングループを追加
- st.session_state.confirmation_logs でセッション中ログを保持
- セッション終了時 CSV 出力

---

**レビュー完了。実装に進んでください。**

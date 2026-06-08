# Phase 5 AI Tally V2.2 確認ログ設計書

**作成日:** 2026-06-08  
**対象:** FAX帳票PDF × Salesforce CSV 照合支援MVP  
**カテゴリ:** 設計書（実装なし）  

---

## 概要

このドキュメントは、AI合計欄 V2.2 の参考判定機能について、**人間が確認・修正・保留した履歴を記録するためのログ設計**です。

**このログの目的：**

- 誰が、いつ、どのページのどの値を見たか
- どのAI値（v3・v22）やCSV値を採用したか
- 手動修正した場合、何に修正したか
- なぜその判定をしたか
- 後から追跡・監査できるようにすること

---

## なぜ確認ログが必要か

### 1. 誤確定防止（コンプライアンス）

このMVPは「OCRを100%当てるツール」ではなく、**確認支援ツール**です。給与評価に直結するため、人間の最終判定証跡が必須。

### 2. 作業効率化の測定

- 確認時間削減率（Before/After）
- auto_confirm_candidate の実確定率
- review_required の確認件数
- 手動修正の頻度・パターン

### 3. AI改善のフィードバック

ユーザーの判定パターンから、次版の学習データを改善。

### 4. 説明責任・トレーサビリティ

「なぜこの値にしたのか」を説明可能に。

---

## ログ対象イベント（12個）

| イベント名 | 意味 | 対応するuser_action |
|-----------|------|----------|
| v22_section_viewed | V2.2参考判定セクション表示 | view |
| v22_csv_downloaded | CSV ダウンロード | download_csv |
| auto_candidate_confirmed | auto_confirm_candidate 確認済み | confirm |
| review_item_confirmed | review_required 確認済み | confirm |
| manual_value_corrected | 値を手動修正 | correct |
| csv_value_selected_as_final | CSV値を採用 | select_csv |
| pdf_value_selected_as_final | PDF値を採用 | select_pdf |
| v3_value_selected_as_final | v3値を採用 | select_v3 |
| v22_value_selected_as_final | v22値を採用 | select_v22 |
| decision_deferred | 判定を保留 | defer |
| item_skipped | スキップ | skip |
| classification_overridden | 分類を上書き | override_classification |

---

## ログ項目定義（27項目）

| # | 項目名 | 型 | 必須 | 説明 |
|---|--------|-----|------|------|
| 1 | log_id | str | ✅ | LOG_YYYYMMDD_序番_P##_フィールド |
| 2 | timestamp | ISO8601 | ✅ | 2026-06-08T14:32:45+09:00 |
| 3 | user_id | str | 任意 | ユーザー識別子 |
| 4 | operator_name | str | 任意 | 氏名（任意） |
| 5 | session_id | str | 任意 | Streamlit session ID |
| 6 | page | int | 任意 | ページ番号 |
| 7 | store_name | str | 任意 | 店舗名 |
| 8 | store_code | str | 任意 | 店舗コード |
| 9 | field_code | str | 任意 | AI（固定） |
| 10 | field_name | str | 任意 | AI合計 |
| 11 | v3_value | str/int | 任意 | v3標準版の値 |
| 12 | v22_value | str/int | 任意 | V2.2推定値 |
| 13 | csv_value | str/int | 任意 | CSV値 |
| 14 | final_value | str/int/null | 任意 | 最終値 |
| 15 | confidence | str | 任意 | high / medium / low |
| 16 | classification | str | 任意 | auto_confirm_candidate / review_required |
| 17 | auto_confirm_candidate | bool | 任意 | true/false |
| 18 | review_required | bool | 任意 | true/false |
| 19 | review_reason | str | 任意 | confidence_low / v22_csv_mismatch など |
| 20 | user_action | str | ✅ | view / confirm / correct / ... |
| 21 | user_decision | str | 任意 | accept_v22 / accept_csv / manual_correct / ... |
| 22 | manual_correction_value | str/int/null | 任意 | 修正後の値 |
| 23 | decision_reason | str | 任意 | 判定理由 |
| 24 | before_status | str | ✅ | unreviewed / auto_confirm_candidate / review_required / ... |
| 25 | after_status | str | ✅ | confirmed / corrected / deferred / skipped |
| 26 | raw_response_id | str | 任意 | raw_YYYYMMDD_P##_... |
| 27 | app_version | str | 任意 | Phase5_Step5_prototype |

---

## ステータス遷移

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

**重要:** auto_confirm_candidate は「候補」であり「確定済み」ではない。

---

## user_action と user_decision 定義

### user_action（ユーザーが取った操作）

- view：セクション表示
- download_csv：CSV ダウンロード
- confirm：確認して承認
- correct：値を修正
- select_csv / select_pdf / select_v3 / select_v22：値を選択
- defer：保留
- skip：スキップ
- override_classification：分類上書き

### user_decision（ユーザーが下した判定）

- accept_v22 / accept_csv / accept_pdf / accept_v3：各値を採用
- manual_correct：手動修正（manual_correction_value に値）
- defer：判定保留
- skip：スキップ
- needs_follow_up：追加確認必要

---

## manual_correction_value の扱い

user_decision = manual_correct のときのみ、修正後の値を入力。

例：
\\\
v3_value = 34
v22_value = 3
csv_value = 3
user_action = correct
user_decision = manual_correct
manual_correction_value = 2  ← 修正値
decision_reason = "PDF再確認で2が正しい"
before_status = auto_confirm_candidate
after_status = corrected
\\\

---

## auto_confirm_candidate のログ例

### ケース1：承認

\\\
page,14, v3_value,34, v22_value,3, csv_value,3
confidence,high, classification,auto_confirm_candidate
user_action,confirm, user_decision,accept_v22
before_status,auto_confirm_candidate, after_status,confirmed
decision_reason,AI V2.2は3で正しい。OCR誤読を補正。
\\\

### ケース2：修正

\\\
page,30, v3_value,2, v22_value,1, csv_value,1
confidence,high, classification,auto_confirm_candidate
user_action,correct, user_decision,manual_correct
manual_correction_value,0
before_status,auto_confirm_candidate, after_status,corrected
decision_reason,V2.2は1としたが、PDFを詳細確認したら0が正しい
\\\

### ケース3：保留

\\\
page,14, v3_value,34, v22_value,3, csv_value,3
user_action,defer, user_decision,defer
before_status,auto_confirm_candidate, after_status,deferred
decision_reason,別の確認方法を検討してから
\\\

---

## review_required のログ例

### ケース1：修正して確定

\\\
page,16, v3_value,9, v22_value,2, csv_value,11
confidence,low, classification,review_required, review_reason,confidence_low
user_action,correct, user_decision,manual_correct
manual_correction_value,11
before_status,review_required, after_status,corrected
decision_reason,v3=9は誤読。CSVの11が正しい。PDF再確認済み。
\\\

### ケース2：保留（店舗確認待ち）

\\\
page,16, v3_value,9, v22_value,2, csv_value,11
confidence,low, classification,review_required
user_action,defer, user_decision,needs_follow_up
before_status,review_required, after_status,deferred
decision_reason,店舗に確認が必要。不一致の原因を報告。
\\\

---

## 保留・スキップの扱い

### 保留 (defer)
- after_status = deferred
- 後から再度確認予定
- 件数集計対象

### スキップ (skip)
- after_status = skipped
- 確認なしで先に進む
- 監査対象になる可能性
- 推奨されない

---

## raw_response の扱い

ログには full raw_response を保存しません。

- raw_response_id：参照ID のみ記録
  形式：raw_YYYYMMDD_P##_フィールド_バージョン_連番

理由：
- ログ行サイズ削減
- 日本語を含むため膨大になる
- 監査時は ID から別途取得

---

## 個人情報・セキュリティの扱い

### 記録しない
❌ API キー  
❌ メールアドレス  
❌ 住所詳細  
❌ 従業員個人名（surname）  
❌ raw_response 全文  

### 記録OK
✅ store_code（S001など）  
✅ store_name（店舗名）  
✅ user_id（ID）  
✅ operator_name（任意）  
✅ decision_reason  
✅ raw_response_id  

現状は暗号化・マスキング未実装。将来ステップで検討。

---

## 将来のapp.py実装方針

**このStep 5では実装しません。**

### 実装予定のUI
- [確認済み] [修正] [保留] [スキップ] [分類上書き] ボタン

### セッション管理
- st.session_state.confirmation_logs に保持
- ボタンクリック時に log_id + timestamp 生成
- 確認作業終了時 CSV 保存

### ログ保存先（案）
- 開発環境：data/logs/confirmation_logs_{YYYYMMDD}.csv
- 本番環境：Salesforce / DB / Google Sheets
- セキュリティ：認証後のみ記録

---

## CSV出力方針

### ファイル名
\phase5_ai_tally_v22_confirmation_log_YYYYMMDD_HHMM.csv\

### エンコーディング
UTF-8 with BOM（Excel で日本語表示）

### 項目順
log_id, timestamp, user_id, operator_name, session_id, page, store_name, store_code, field_code, field_name, v3_value, v22_value, csv_value, final_value, confidence, classification, auto_confirm_candidate, review_required, review_reason, user_action, user_decision, manual_correction_value, decision_reason, before_status, after_status, raw_response_id, app_version

---

## 運用上の注意

### ログ記録実装が遅れた場合
- 手動でスプレッドシート記録でも可
- 重要なのは「誰が何を決定したか」の記録

### 利用シーン
1. ジオ様報告：「本日30件確認。auto_confirm 17件確定、review_required 13件（修正5件、保留3件）」
2. AI改善：user_decision 集計から次版データ作成
3. 教訓共有：「confidence_low は human correction が多い。次版で改善」

### 保持期間
- 最低3ヶ月保持
- ジオ様との説明・交渉に必要

---

## 今回実装しないこと

❌ UI ボタン実装  
❌ ログ保存機能  
❌ DB 連携  
❌ ダッシュボード  
❌ 暗号化  
❌ API キー管理  
❌ Salesforce 連携  
❌ 分散トレーシング  

→ Phase 5 Step 6 以降で段階実装

---

**このドキュメントは Phase 5 Step 5 「確認ログ設計書作成」の成果物。**  
**実装は次のステップで行う。**

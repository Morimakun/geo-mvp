# Phase 5 Step 5 AI Tally V2.2 確認ログ設計書

**作成日：** 2026-06-08  
**対象：** AI合計欄V2.2参考判定の確認操作ログ設計（監査・トラブル追跡用）  
**位置づけ：** ログ設計のみ。ログ保存機能の実装は Step 6 以降

---

## 1. 確認ログを残す目的

### 1.1 なぜログが必要か

V2.2は「確認支援ツール」であり、**最終判断は人間が行う**。

以下のシナリオに対応するため、監査ログが必須：

```
1. 誤確定が発生した場合
   → 「いつ、誰が、どう判断したのか」を追跡
   → 原因分析・再発防止の基盤

2. OCR補正の改善効果を測定
   → 「P14型（v3大誤読を修正）をいくつ見つけたか」
   → V2.2の実績を定量化

3. Salesforce更新タイミング差の検証
   → 「P2/P11/P28での確認パターン」
   → タイミング差仮説の検証

4. confidence low の実績確認
   → 「低信頼度ページを人間がどう判断したか」
   → confidence threshold の妥当性評価

5. UI改善のヒント
   → 「どのページで悩んだか」「スキップ率は」
   → 次版UIの改善方向

6. ジオ様への説明・報告
   → 「確認支援によって実務が改善した」
   → 定量的なBefore/After示せる
```

### 1.2 ログの性格

- **監査用**：確認操作の追跡・原因分析
- **分析用**：V2.2の改善効果測定
- **改善用**：UI・UX・ロジック改善のヒント
- ❌ **自動確定用ではない**：確認結果はSalesforce自動更新に使わない
- ❌ **生データ保存ではない**：raw_response全文は記録しない

---

## 2. ログ対象イベント（9種類）

### A. auto_confirm_candidate を確認済みにした

**誰：** 確認担当者  
**何：** auto_confirm 候補ページを確認して「OK」判定  
**記録する値：**
- ページID、store_name
- v3値、v22値、CSV値
- 判定「confirmed」
- 決定理由「auto_confirm一致・確認済み」

**ログ例：** P1, 小倉, v3=5/v22=5/csv=5 → confirmed

### B. review_required を確認済みにした

**誰：** 確認担当者  
**何：** 要確認ページを人間が確認して値を決定  
**記録する値：**
- ページID、store_name
- v3値、v22値、CSV値
- 最終確定値
- 判定「confirmed」
- 決定理由「差分確認・CSV値採用」など

**ログ例：** P2, イオン大日, v3=0/v22=0/csv=2 → final=2, "Salesforce更新タイミング差"

### C. AI値を手動修正した

**誰：** 確認担当者  
**何：** PDF読取値やCSV値が誤っていると判断し、手動入力で修正  
**記録する値：**
- ページID、store_name
- v3値、v22値、CSV値
- 修正前の推奨値
- 修正値（手入力）
- 判定「corrected」
- 決定理由「PDF解析で判明した正値」など

**ログ例：** P12, 心斎橋, v3=0/v22=1/csv=2 → corrected to 3, "PDF目視確認で3確認"

### D. CSV値を正と判断した

**誰：** 確認担当者  
**何：** PDF読取との差分を見て、CSV側が正しいと判断  
**記録する値：**
- ページID、store_name
- v3値、v22値、CSV値
- 判定「csv_is_correct」
- 決定理由「CSV確認・PDF記入ミスの可能性」など

**ログ例：** P20, 梅田, v3=6/v22=4/csv=5 → csv_is_correct, "内訳とCSVが一致"

### E. PDF値を正と判断した

**誰：** 確認担当者  
**何：** PDF読取を確認し、CSV値が古いか誤っていると判断  
**記録する値：**
- ページID、store_name
- v3値、v22値、CSV値
- PDF目視値
- 判定「pdf_is_correct」
- 決定理由「PDF再確認・CSV値は古い」など

**ログ例：** P15, 枚方, v3=4/v22=2/csv=2 → pdf_is_correct, "内訳精査でPDF=2確認"

### F. 判定保留にした

**誰：** 確認担当者  
**何：** 確認が必要だが、その場では判断できず、後で改めて確認するように保留  
**記録する値：**
- ページID、store_name
- v3値、v22値、CSV値
- 判定「pending」
- 保留理由「Salesforceタイミング差の可能性・48h後再確認」など

**ログ例：** P2, イオン大日 → pending, "Salesforceのタイムスタンプ確認待ち"

### G. スキップした

**誰：** 確認担当者  
**何：** auto_confirm 候補だが、初期導入のため確認不要と判定してスキップ  
**記録する値：**
- ページID、store_name
- v3値、v22値、CSV値
- 判定「skipped」
- スキップ理由「auto_confirm確実・初期導入段階で時間優先」など

**ログ例：** P1, 小倉 → skipped, "auto_confirm確認済み・次月抜き打ちチェック対象"

### H. CSVダウンロードした

**誰：** 確認担当者（または管理者）  
**何：** V2.2参考判定テーブルをCSV形式でダウンロード  
**記録する値：**
- timestamp
- operator_name
- action「download_csv」
- ダウンロード日時
- 対象ファイル「ai_tally_v22_review_flags.csv」

**ログ例：** 2026-06-08 15:30:45, スタッフA → download_csv, "本日分の確認用"

### I. V2.2参考判定を表示した

**誰：** 確認担当者  
**何：** app.pyで「[4] AI合計欄V2.2参考判定」セクションを開いて参考情報を表示  
**記録する値：**
- timestamp
- operator_name
- action「view_detail」
- セッションID
- フィルター選択（「すべて」「自動確定のみ」など）

**ログ例：** 2026-06-08 14:00:00, スタッフB, session=abc123 → view_detail, filter="review_required"

---

## 3. ログに残すべき項目（24項目）

### 基本情報（6項目）

| # | 項目 | 型 | 説明 | 例 |
|----|------|-----|------|-----|
| 1 | timestamp | datetime | ログ記録日時（ISO 8601） | 2026-06-08T15:30:45Z |
| 2 | user_id | string | ユーザーID/スタッフコード | STAFF001 |
| 3 | operator_name | string | 確認担当者名 | スタッフA |
| 4 | session_id | string | セッションID | abc123xyz |
| 5 | app_version | string | app.pyバージョン | 1.0.0 |
| 6 | source_app | string | 操作元（"app_v1"など） | app_v1 |

### ページ・帳票情報（7項目）

| # | 項目 | 型 | 説明 | 例 |
|----|------|-----|------|-----|
| 7 | page_id | string | ページID | P14 |
| 8 | page_number | int | ページ番号 | 14 |
| 9 | store_name | string | 店舗名 | 小倉町 |
| 10 | store_code | string | 店舗コード | 12345 |
| 11 | source_file_pdf | string | ソースPDFファイル名 | geo_20260608_001.pdf |
| 12 | source_file_csv | string | ソースCSVファイル名 | salesforce_20260608.csv |
| 13 | business_date | date | 営業日 | 2026-06-07 |

### AI合計欄の値（7項目）

| # | 項目 | 型 | 説明 | 例 |
|----|------|-----|------|-----|
| 14 | v3_ai_value | int or null | v3読取値 | 34 |
| 15 | v22_estimated_value | int or null | V2.2推定値 | 3 |
| 16 | csv_ai_value | int or null | CSV AI列値 | 3 |
| 17 | final_value | int or null | 最終確定値 | 3 |
| 18 | confidence | string | V2.2信頼度 | medium |
| 19 | classification | string | V2.2分類 | ocr_correction |
| 20 | review_reason | string | 確認理由 | v3大誤読を修正 |

### 確認操作（4項目）

| # | 項目 | 型 | 説明 | 例 |
|----|------|-----|------|-----|
| 21 | user_action | string | 確認担当者の操作 | confirm_auto_candidate |
| 22 | user_decision | string | 最終判定 | confirmed |
| 23 | decision_reason | string | 判定の根拠 | CSV一致・確認済み |
| 24 | notes | text | 追加メモ | 初期導入期間・確認推奨 |

### オプション項目（追加）

| # | 項目 | 型 | 説明 | 例 |
|----|------|-----|------|-----|
| 25 | auto_confirm_candidate | boolean | auto_confirm候補フラグ | true |
| 26 | review_required | boolean | 要確認フラグ | false |
| 27 | manual_correction_value | int or null | 手動修正値 | 3 |
| 28 | before_status | string | 変更前の状態 | auto_confirm_pending |
| 29 | after_status | string | 変更後の状態 | confirmed |
| 30 | raw_response_hash | string | V2.2応答のハッシュ値 | abc123def456 |

---

## 4. user_action の候補（9種類）

確認担当者が取りうるアクション：

| action | 説明 | 該当ページ | ログに残すべき |
|--------|------|-----------|--------------|
| **confirm_auto_candidate** | auto_confirm候補を「確認・OK」 | P1, P14, P30 | ✅ |
| **confirm_review_item** | review_required を人間確認後「確定」 | P16, P20 | ✅ |
| **manual_correct** | AI値を手動修正 | P12 | ✅ |
| **accept_csv_value** | CSV値を「正」と判定 | P2, P11 | ✅ |
| **accept_pdf_value** | PDF値を「正」と判定 | P15 | ✅ |
| **mark_pending** | 判定を「保留」 | P2 | ✅ |
| **skip** | auto_confirm をスキップ | P1（初期導入フェーズ） | ✅ |
| **download_csv** | CSV をダウンロード | （セッション全体） | ✅ |
| **view_detail** | 詳細情報を表示 | （セッション全体） | ⚠️ オプション |

---

## 5. user_decision の候補（7種類）

確認担当者が下す最終判定：

| decision | 説明 | 次アクション | 例 |
|----------|------|-----------|-----|
| **confirmed** | 確認済み・値確定 | Salesforce入力対象外（ログに記録） | P1, P14 |
| **corrected** | 手動修正した | 手動修正値をSalesforceへ | P12：修正値=3 |
| **csv_is_correct** | CSV側が正 | CSV値をそのまま採用 | P20 |
| **pdf_is_correct** | PDF側が正 | PDF値をSalesforceへ更新 | P15 |
| **pending** | 判定保留 | 後日改めて確認 | P2 |
| **skipped** | スキップ（確認不要） | そのまま進める | P1（初期段階） |
| **needs_follow_up** | フォローアップ必要 | 別途確認・修正 | P16（要強制確認） |

---

## 6. 確認ログ設計例（イベント別）

### ログパターン A: auto_confirm確認

```
timestamp: 2026-06-08T15:30:45Z
user_id: STAFF001
operator_name: スタッフA
session_id: abc123xyz
page_id: P1
store_name: 小倉
v3_value: 5
v22_value: 5
csv_value: 5
final_value: 5
confidence: medium
classification: auto_confirm
auto_confirm_candidate: true
review_required: false
user_action: confirm_auto_candidate
user_decision: confirmed
decision_reason: CSV一致・確認済み
notes: 通常確認
```

### ログパターン B: review_required確認（CSV値採用）

```
timestamp: 2026-06-08T15:32:15Z
user_id: STAFF001
operator_name: スタッフA
session_id: abc123xyz
page_id: P2
store_name: イオン大日
v3_value: 0
v22_value: 0
csv_value: 2
final_value: 2
confidence: medium
classification: review
auto_confirm_candidate: false
review_required: true
review_reason: blank判定だがCSV>0
user_action: accept_csv_value
user_decision: csv_is_correct
decision_reason: Salesforce更新タイミング差の可能性
notes: 48h後の再確認検討
```

### ログパターン C: OCR補正候補確認

```
timestamp: 2026-06-08T15:35:00Z
user_id: STAFF001
operator_name: スタッフA
session_id: abc123xyz
page_id: P14
store_name: 小倉町
v3_value: 34
v22_value: 3
csv_value: 3
final_value: 3
confidence: medium
classification: ocr_correction
auto_confirm_candidate: true
review_required: false
user_action: confirm_auto_candidate
user_decision: confirmed
decision_reason: OCR補正確認・v3大誤読を修正
notes: V2.2改善効果・初期導入期間確認推奨
```

### ログパターン D: 手動修正

```
timestamp: 2026-06-08T15:40:30Z
user_id: STAFF001
operator_name: スタッフA
session_id: abc123xyz
page_id: P12
store_name: 心斎橋
v3_value: 0
v22_value: 1
csv_value: 2
manual_correction_value: 3
final_value: 3
confidence: medium
classification: review
auto_confirm_candidate: false
review_required: true
review_reason: v22とCSV不一致
user_action: manual_correct
user_decision: corrected
decision_reason: PDF目視確認で3が正
notes: 複合問題・内訳精査により確定
```

---

## 7. CSV出力案

### ファイル形式

**ファイル名：** `ai_tally_v22_confirmation_log.csv`  
**エンコーディング：** UTF-8 with BOM（日本語対応）  
**レコード数：** 確認ごと（1ページ 1行以上）

### 列順序（推奨）

```
timestamp,user_id,operator_name,session_id,app_version,
page_id,page_number,store_name,store_code,business_date,
v3_value,v22_value,csv_value,final_value,
confidence,classification,review_reason,
auto_confirm_candidate,review_required,
user_action,user_decision,decision_reason,
manual_correction_value,
source_file_pdf,source_file_csv,
notes
```

### 追記型運用

```
初回：ヘッダー + 30行（1日分）を新規作成
2日目以降：既存ファイルに追記
   ↓
ログ行数が増え続ける → 月ごとにアーカイブ
   ↓
long_term_log_202606.csv
long_term_log_202607.csv
...
```

---

## 8. 将来的なDB化設計案

### テーブル設計（参考）

**テーブル名：** `ai_tally_confirmation_log`

```sql
CREATE TABLE ai_tally_confirmation_log (
  log_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  timestamp DATETIME NOT NULL,
  
  -- User
  user_id VARCHAR(50) NOT NULL,
  operator_name VARCHAR(100),
  session_id VARCHAR(100),
  
  -- Page/Store
  page_id VARCHAR(10) NOT NULL,
  page_number INT,
  store_name VARCHAR(100),
  store_code VARCHAR(50),
  business_date DATE,
  
  -- AI Values
  v3_value INT,
  v22_value INT,
  csv_value INT,
  final_value INT,
  
  -- V2.2 Metadata
  confidence VARCHAR(10),
  classification VARCHAR(50),
  review_reason TEXT,
  
  -- Flags
  auto_confirm_candidate BOOLEAN,
  review_required BOOLEAN,
  
  -- Confirmation
  user_action VARCHAR(50) NOT NULL,
  user_decision VARCHAR(50) NOT NULL,
  decision_reason TEXT,
  manual_correction_value INT,
  
  -- Audit
  app_version VARCHAR(20),
  source_file_pdf VARCHAR(255),
  source_file_csv VARCHAR(255),
  raw_response_hash VARCHAR(64),
  
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  
  INDEX idx_page (page_id),
  INDEX idx_timestamp (timestamp),
  INDEX idx_user (user_id),
  INDEX idx_decision (user_decision)
);
```

### インデックス戦略

```
PRIMARY KEY: log_id（全件検索）
INDEX: page_id（「P14での確認パターン」検索）
INDEX: timestamp（日付範囲検索）
INDEX: user_id（「スタッフAの判定」検索）
INDEX: user_decision（「confirmed件数」集計）
```

### 集計クエリ例

```sql
-- 1日の確認数集計
SELECT user_id, COUNT(*) as confirmed_count
FROM ai_tally_confirmation_log
WHERE DATE(timestamp) = '2026-06-08'
GROUP BY user_id;

-- V2.2改善効果測定
SELECT COUNT(*) as ocr_fixed_count
FROM ai_tally_confirmation_log
WHERE classification = 'ocr_correction'
  AND user_decision = 'confirmed'
  AND v3_value != v22_value;

-- P16型（低信頼度）の人間判定パターン
SELECT user_decision, COUNT(*) as count
FROM ai_tally_confirmation_log
WHERE page_id = 'P16'
GROUP BY user_decision;
```

---

## 9. app.py実装時の注意点

### 9.1 初期段階（Step 5-6）

```
✅ CSVログ保存でよい（手軽・検索可能）
❌ DB化は後回し（複雑性増加）
✅ 追記型にする（既存ログを上書きしない）
✅ ログは監査用（自動Salesforce更新に使わない）
```

### 9.2 ログ記録のライフサイクル

```
1. ユーザーが確認操作（confirm/correct/skip）
   ↓
2. app.py がログ行をメモリに組立
   ↓
3. CSVファイルに追記（flush）
   ↓
4. 確認完了メッセージを表示
   ↓
5. 監査・分析時にCSVを読み込み
```

### 9.3 raw_response の取り扱い

```
❌ raw_response 全文を記録（容量大・機密情報含む）
✅ raw_response_hash（参照用）のみ記録
   → 必要時は別のDB/ファイルで管理
   → hash で該当レスポンスを特定可能
```

### 9.4 個人情報・機密情報

```
❌ 個人の手書き判読内容を記録しない
✅ ユーザーIDと判定結果のみ記録
✅ 「なぜそう判定したか」は notes に簡潔に記録
❌ PDF画像・CSVセル値そのものは記録しない
```

### 9.5 Salesforce連携との分離

```
ログシステム（監査用）
   ↑
   ├─ 確認操作を記録
   └─ 傾向分析・改善に使用

↓（別処理）↓

Salesforce 自動更新（本番用）
   ├─ ユーザーの最終判定を読み取り
   └─ 値をSalesforceへ書き込み

⚠️ ログに基づいて自動更新しない
⚠️ ユーザーの明示的な確定ボタンで更新
```

---

## 10. ログ保存期間の考え方

### 保持期間案

| ログタイプ | 保持期間 | 理由 |
|-----------|--------|------|
| 日次ログ（active） | 6か月 | トラブル対応・傾向分析 |
| 月次アーカイブ | 2年 | 監査・コンプライアンス |
| 年次集計 | 永続 | 改善効果の長期追跡 |

### アーカイブ方針

```
2026-06-30 終了時：
  log_202606.csv（6月分）を別フォルダに移動
  log_202607.csv（7月分）を新規作成開始

2027-06-30 終了時：
  log_202606.csv → archive/log_2026_h1.csv に集約
  log_202607.csv → archive/log_2026_h1.csv に集約
  ...
```

---

## 11. ジオ様への説明方針

### 説明資料に含めるべき内容

#### 1. ログの目的（透明性）

```
「確認支援ツールなので、すべての確認操作を記録しています。
 これは以下の目的で保存されます：

 ✅ トラブル時の原因追跡
 ✅ V2.2の改善効果測定（どのページで役立ったか）
 ✅ 操作者の負荷削減効果定量化
 ✅ 将来的なUI改善の参考

 ❌ 個人評価・監視の目的ではありません
```

#### 2. ログに残る情報（具体例）

```
「以下がログに記録されます：
 - いつ（timestamp）
 - 誰が（operator_name）
 - どのページを（page_id）
 - どう判定したか（user_decision）
 - その理由（decision_reason）
 
 記録されません：
 - 個人情報（社員ID等、operator_nameのみ）
 - PDF画像・CSVセル値そのもの
 - 手書きテキスト詳細
```

#### 3. 運用ルール（信頼醸成）

```
「ログは監査用であり、自動Salesforce更新に使いません。
 最終決定は常に人間の明示的なボタン操作です。

 また、ログは6か月単位で管理し、
 個人を特定された形での長期保存はしません。」
```

---

## 12. 実装前チェックリスト

- [ ] ログ対象イベント（9種類）の定義が確定
- [ ] ログ項目（24+）の定義が確定
- [ ] user_action / user_decision の型が定義
- [ ] CSV形式の列順序が決定
- [ ] 個人情報の取り扱いが定義
- [ ] ジオ様への説明文言が確定
- [ ] DB化時期のロードマップが確定
- [ ] ログ保持期間が確定
- [ ] Salesforce連携との分離が設計されている

---

**設計状態：** ✅ ログ設計完了  
**対象：** AI合計欄V2.2の確認操作ログ（監査・分析用）  
**本体コード：** 未編集（app.py ログ保存機能未実装）  
**Vision API：** 未再実行  
**次ステップ：** Phase 5 Step 6（app.py へのログ保存機能実装）

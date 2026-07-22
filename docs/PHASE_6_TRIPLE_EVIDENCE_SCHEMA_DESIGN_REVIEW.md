# Phase 6: 三者証拠スキーマ 設計レビュー（第4版・最終）

作成日: 2026-07-20（第4版）
ステータス: **コード変更前の最終設計レビュー。承認後、Step1（CSV candidate resolver）実装へ進む。コード・GT・Excel・検証HTMLは未変更。**
参照元: [PHASE_6_25ITEM_PILOT_RESULT_AND_TRIPLE_CROSSCHECK_SPEC.md](./PHASE_6_25ITEM_PILOT_RESULT_AND_TRIPLE_CROSSCHECK_SPEC.md) Section 5

## 改訂履歴

- **第2版**：8点の修正指示を反映（責務分離、CSV取得済みの訂正、正本/派生値、正の字観測根拠、confidence分離、店舗コードマスター格下げ、実装配置の訂正、テストケース具体化）
- **第3版**：CSV結合仕様の追加修正。①P23の2行は既知パターンの再確認と位置づけ直し、②CSV結合結果を`csv_match_status`等の構造で保持、③P32/P41/P59/P66のCSV結合証跡を追記、④JOINキーの営業日を`selected_business_date`（外部設定の正本）に変更、⑤実装順序をStep1〜5で明確化
- **第4版（本版）**：CSV結合仕様のさらなる修正。①P66：候補行1件でも店舗コードが未確認参考データ経由の場合は`reference_match_unverified`とし`unique_match`に昇格させない、②P32：AI抽出コード単独をJOINキーにせず、exact match失敗後に編集距離ベースの近似探索（`near_match_candidates`）を行う設計に変更（循環参照回避）、③「実装した」ではなく「設計書へ定義した」という表現に統一、④`row_number`をExcel 1始まり・ヘッダー込みと明記し、`data_row_index`（0始まり・ヘッダー除く）を別フィールドとして追加

---

## 1. CSVデータの現状

Salesforce CSVエクスポート（Excel形式）は`data/phase6_received/`に2026-07-07受領・格納済み。各ファイルの`CSV`シート（283列）が該当。col1=法人・店舗(取扱コード)、col36=紹介総数、col105=お声がけ総数、col283=日付（Excelシリアル値）を実際に開いて確認済み（第2版で検証済み、変更なし）。

| ファイル | ページ範囲（8.1節の対応） |
|---|---|
| `SFAエクスポートマスター0627b.xlsx` | P01〜P28 |
| `SFAエクスポートマスター0626b.xlsx` | P29〜P48 |
| `SFAエクスポートマスター0625nn.xlsx` | P49〜P66 |

### 1.1 P23の2行構成：既知パターンの実データ再確認（位置づけを訂正）

**訂正：これは新規発見ではない。** 既存ドキュメント`docs/PHASE_6_CLIENT_CONFIRMATION_ITEMS.md`（先方確認プロセスの記録）に、**鶴見緑地・ニトリモール枚方（いずれも6/27）で「店舗」「イベント」2枚のPDF帳票提出に対してCSVも2行出力される構造がすでに確認済み**と明記されている（同文書16行目、62-73行目）。P23（ニトリモール枚方、6/27）のCSV2行（26行目intro=6, 27行目intro=5）は、**この既知パターンが今回の実データでも再現していることの確認**である。

ただし、同じ確認プロセスで並行して判明している通り（`docs/PHASE_6_SFA_EXPORT_SCHEMA_CHECK.md` 32-39行目）、**CSV側の283列スキーマには「店頭／イベント」を区別する列が存在しない**（先方への確認質問として送付済み・未回答）。したがって、2行のうちどちらが将大さんの読んだPDF帳票（P23）に対応するかを、現在確認済みのCSV列だけで機械的に判別することはできない。

**設計方針：店舗コード＋営業日で複数行がヒットした場合は`multiple_unresolved`として扱う。** どちらの行が正しいかを推測で選ばない（2節）。

### 1.2 店舗コード参考データについて

CSVブック内の`入力マスター`シート（店舗名／取扱コード／スタッフ名／フリガナ、25店舗分）は正式なマスターとして確認が取れていない。6節の「参考照合」レベルの扱いに留める。

---

## 2. CSV結合結果の構造（設計定義。コードは未実装）

`csv_value`を常に単一値として扱わず、以下の構造で保持する設計とする。**Vision抽出JSON（3節）には含めない。** 抽出後の別ステップ（CSV結合処理）でのみ生成する。**本節はスキーマの定義であり、コードとしての実装はまだ行っていない（12節Step1で着手する）。**

```jsonc
"csv_evidence": {
  "csv_match_status": "unique_match" | "multiple_unresolved" | "not_found"
                     | "resolved_by_rule" | "reference_match_unverified",
  "csv_candidate_rows": [
    {
      "source_file": "<例: SFAエクスポートマスター0626b.xlsx>",
      "sheet_name": "CSV",
      "row_number": <int>,      // Excel上の1始まり・ヘッダー行込みの行番号（2.3節）
      "data_row_index": <int>,  // ヘッダーを除いたデータ行のみの0始まり連番（2.3節）
      "store_code": "<例: AU1K4330093>",
      "business_date": "<例: 2026-06-26>",
      "business_mode": "store" | "event" | "unknown",
      "intro_total": <int|null>,
      "voice_callout_total": <int|null>
    }
    // 該当行が複数あれば複数要素
  ],
  "near_match_candidates": [
    {
      "source_file": "<例: SFAエクスポートマスター0626b.xlsx>",
      "sheet_name": "CSV",
      "row_number": <int>,
      "data_row_index": <int>,
      "store_code": "<CSV上の候補コード>",
      "edit_distance": <int>,
      "difference_description": "<例: '連続する3の1桁欠落候補'>",
      "intro_total": <int|null>,
      "voice_callout_total": <int|null>
    }
    // exact matchが0件のときのみ、編集距離ベースで探索した近似候補（2.4節）
  ],
  "resolved_csv_value": {
    "intro_total": <int|null>,
    "voice_callout_total": <int|null>
  },
  "resolution_basis": "<一意に決まった場合、またはunverified/near_matchとして保留した理由>"
}
```

### 2.1 `csv_match_status`の確定ルール

| ステータス | 条件 | `resolved_csv_value` |
|---|---|---|
| `unique_match` | 店舗コード＋`selected_business_date`（4節）で候補行が1件、かつ結合キーの店舗コードが確定情報源（帳票に直接印字された値）に基づく | 候補行の値 |
| `multiple_unresolved` | 候補行が2件以上あり、`business_mode`等で一意に絞り込めない（1.1節のP23が該当） | **必ずnull** |
| `not_found` | exact matchの候補行が0件（2.4節の近似探索は別途`near_match_candidates`に記録） | null |
| `resolved_by_rule` | 候補行は複数だが、あらかじめ確認・合意した機械的ルールで一意に絞り込めた場合（現時点でそのようなルールは未確立。将来、先方からの回答等でルール化された場合に使用する予約値） | ルール適用後の値 |
| `reference_match_unverified` | 候補行が1件でも、結合キーの店舗コードが**未確認の参考データ経由で解決された**場合（10節のP66が該当） | **必ずnull** |

**`business_mode`は現在のCSV列からは判別不能なため、当面すべての候補行で`"unknown"`固定になる。** これが1.1節のP23が`multiple_unresolved`になる直接の理由。

### 2.2 `multiple_unresolved`の場合の下流処理（確定）

- `resolved_csv_value = null`
- **三者一致（`three_way_match`）とは判定しない**
- `review_required = true`
- `review_reasons`に`"csv_multiple_unresolved"`を追加し、`csv_candidate_rows`をそのまま監査用に保持する

### 2.3 `row_number`の定義（明記）

`row_number`は**Excel上の行番号（1始まり、ヘッダー行を含む）**である。例：ヘッダーが1行目、最初のデータ行が2行目。本設計レビュー内でこれまで「10行目」等と記載してきた数値はすべてこの定義に基づく（openpyxlの`iter_rows`が返す1始まりの行番号と一致）。

ヘッダーを除いた純粋なデータ行の連番が必要な処理（例：候補の一覧表示順）のためには、別フィールド`data_row_index`（0始まり、ヘッダー行を含まない）を用意する。両者は**混同しないよう別フィールドとして保持する**。

### 2.4 `reference_match_unverified`：店舗コード情報源による格下げ（P66対応）

`csv_match_status`を`unique_match`にしてよいのは、**結合キーの店舗コードが帳票から直接確定できる情報源（AU1K印字＋手書きボックスの直接読み取り）に基づく場合のみ**。旧帳票のように店舗コードが印字されず、店舗名からの変換（未確認の`入力マスター`シート等）を経由してコードを得た場合は、候補行が1件であっても`reference_match_unverified`とし、`unique_match`/`resolved_by_rule`には昇格させない。

この場合：
- `resolved_csv_value = null`
- `review_required = true`
- `csv_candidate_rows`は**参考表示のみ**（三者一致の算入対象にしない）
- `resolution_basis = "ai_store_name_plus_unverified_reference_master"`

### 2.5 店舗コードの近似一致探索（P32対応、循環参照回避）

店舗コードのCSV結合では、**AI抽出コードだけを唯一のJOINキーとして使わない**。以下の順で処理する。

1. **exact match検索**：AI抽出コード（正規化後）で`csv_candidate_rows`を検索
2. 0件の場合：`selected_business_date`に対応するCSVシート内の全店舗コードを候補集合として取得
3. 候補集合の各コードとAI抽出コードとの**編集距離**（桁数差・1文字挿入／欠落を含む）を計算し、閾値内（例：編集距離1〜2）のものを`near_match_candidates`に記録
4. **近似一致だけで自動修正・自動確定はしない。** `csv_match_status`は`not_found`のまま（1で候補が0件だったため）、`near_match_candidates`に近似候補を保持し、`review_required = true`とする

**P32の期待結果**：AI抽出コード`AU1K430093`でexact matchは0件（`not_found`）。`selected_business_date`=2026-06-26のCSV内で編集距離探索を行うと`AU1K4330093`が編集距離1（連続する「3」の1桁欠落）で`near_match_candidates`に入る。これだけでは自動確定せず、`review_required=true`のまま人手確認へ回す。

---

## 3. Vision抽出JSONに含めるフィールド（責務分離）

```jsonc
{
  // ...既存の店舗コード等の項目は維持（5節）...

  "intro_evidence": {
    "written_total_value": <int|null>,
    "written_total_status": "confirmed" | "candidate" | "unreadable",
    "written_total_confidence": "high" | "medium" | "low",

    "tally_observation_status": "marks_present" | "no_marks_observed" | "unreadable" | "not_applicable",
    "complete_five_groups": <int|null>,
    "remainder_strokes": <int|null>,
    "tally_count": <int|null>,
    "tally_confidence": "high" | "medium" | "low" | null,
    "tally_notes": "<判読困難箇所の説明。問題なければnull>",
    "tally_components": "<観察した個別行の内訳メモ。任意>"
  },
  "voice_evidence": { /* intro_evidenceと同一構造 */ },

  "store_code_confidence": "high" | "medium" | "low"
}
```

**`csv_value`および2節の`csv_evidence`構造はこの出力に一切含めない。** Vision抽出は「帳票から何を読んだか」だけを報告する責務に限定する。CSV結合は独立した後段処理（7節Step1）で行う。

---

## 4. 営業日の扱い（JOINキーの正本を訂正）

**訂正：CSV結合に使う営業日は、AI OCRが帳票から読んだ`date`ではなく、外部設定された`selected_business_date`を正本とする。**

| ページ範囲 | `selected_business_date` |
|---|---|
| P01〜P28 | 2026-06-27 |
| P29〜P48 | 2026-06-26 |
| P49〜P66 | 2026-06-25 |

OCRで読んだ`date`フィールドは、既存プロンプト（`phase6_stage3_full.py` L253-255）でも「照合キーには使用しないこと」と明記されており、本設計もこれを踏襲する。OCR営業日は評価・参考情報としてのみ保持し、CSV結合のJOINキーには使わない。

（本設計レビュー内で先に示したP32/P41/P59/P66/P23のCSV照合作業は、結果として`selected_business_date`の対応表と一致するファイルを選んで実施していたことを確認済み。）

---

## 5. 正本と派生値

### 5.1 正本

- `intro_evidence.written_total_value`
- `voice_evidence.written_total_value`

### 5.2 既存互換フィールド（派生値、独立保存しない）

- `intro_total`
- `voice_callout_total`

**正本から都度計算する派生プロパティとし、別途書き込み・更新しない。**

```python
def intro_total(record):
    return record["intro_evidence"]["written_total_value"]

def voice_callout_total(record):
    return record["voice_evidence"]["written_total_value"]
```

正本を更新すれば既存互換フィールドは自動的に追従するため、値が乖離する構造にはならない。`intro_total_candidate`も同様に`written_total_status == "candidate"`時の`written_total_value`から派生させる。

---

## 6. 正の字の観測根拠

| フィールド | 意味 |
|---|---|
| `tally_observation_status` | 観察結果（4値：`marks_present` / `no_marks_observed` / `unreadable` / `not_applicable`） |
| `complete_five_groups` | 完成した「正」の字（5画1組）の個数 |
| `remainder_strokes` | 最後の未完成の正の字の画数（0〜4） |
| `tally_count` | 算出された合計画数 |
| `tally_confidence` | 正の字読み取り自体の確信度 |
| `tally_notes` | 判読困難箇所のメモ |
| `tally_components` | 観察した個別行の内訳（任意、監査用） |

**計算式**：`tally_count = complete_five_groups * 5 + remainder_strokes`（例：1組+2画 → 5+2=7、10節テスト参照）

**数値化してよい条件**：`tally_observation_status == "marks_present"`の場合のみ。それ以外（`no_marks_observed` / `unreadable` / `not_applicable`）は`tally_count`を含め**すべてnull**。`no_marks_observed`を`0`へ変換する処理は実装しない。

---

## 7. confidenceの分離

`page_overall_confidence`（1回のAPI応答に1つだけ付与される既存値）は個別フィールドの確信度に流用しない。最低限、以下を独立フィールドとして持たせる。

- `written_total_confidence`（紹介・お声がけそれぞれ）
- `tally_confidence`（同上）
- `store_code_confidence`

現行プロンプトは全項目共通の`confidence`1つしか出力しないため、プロンプト自体の修正が必要（8.2節Step3）。

---

## 8. 店舗コードマスターの扱い

「店舗名 スタッフ名.xlsx」相当のデータ（1.2節の`入力マスター`シート）は正式マスターとして確認が取れていない。店舗コードの検証は以下の3段階に限定し、**「マスター一致による確定」という表現・ステータス値は使わない**。

| 段階 | 内容 | 出力ステータス値 |
|---|---|---|
| 1. 形式チェック | `AU1K`プレフィックス＋想定パターンに合致するか | `format_valid` / `format_invalid` |
| 2. 桁数チェック | 可変部分の文字数が期待桁数（7桁、9.3節参照）と一致するか | `digit_count_valid` / `digit_count_invalid` |
| 3. 参考照合 | CSV `col1`や`入力マスター`シートの既知コード一覧に存在するか | `known_candidate_match` / `no_candidate_match` / `reference_data_unavailable` |

3段階とも参考情報として`review_reasons`に積み増すだけで、これらの結果だけで自動確定（`review_required=false`）にはしない。

---

## 9. 実装配置

### 9.1 現状の正確な表現

「本番コードが存在しない」ではなく、**`outputs/phase6_temp/phase6_stage3_full.py`（1011行）は検証用の一時パイプラインであり、初期版の正式な実装配置はまだ確定していない。** プロジェクトルートの`app.py`等は本フェーズ以前の別データセット向けであり、本フェーズの正式実装先ではない。

### 9.2 モジュール分割案

| モジュール | 責務 |
|---|---|
| **extraction schema / prompt** | Vision抽出プロンプトとJSON出力スキーマの定義（3節） |
| **evidence normalization** | 抽出結果の正規化（AU1Kプレフィックス処理、cleaned/comparison_key計算等） |
| **CSV mapping** | `SFAエクスポートマスター*.xlsx`の`CSV`シート読み込み＋`csv_match_status`解決（2節） |
| **triple evidence comparison** | written/tally/csvの3系統から`evidence_comparison_result`を算出（11節） |
| **review routing** | `evidence_comparison_result`から`review_required`/`review_reasons`を決定 |
| **test fixtures** | P32/P41/P59/P66/P23等の実データを使った固定テストケース（12節） |

物理的な配置先（新規ディレクトリ／`phase6_temp`内分割）は未確定（13節）。

### 9.3 店舗コード桁数チェック

Vision API呼び出しとは別の決定論的Python後処理として、`evidence normalization`モジュール内に実装する。期待桁数「7」はサンプリング6ページの画像確認による暫定値で、新帳票全51ページでの確認は未実施。

---

## 10. CSV結合の証跡（P32・P41・P59・P66・P23）

将大さんのご指摘に基づき、page-対応メタデータ・店舗名目視・AI抽出値を区別して明記する。

### P32（布施）：近似一致探索の実例（2.5節）

**重要：AI抽出コード`AU1K430093`を唯一のJOINキーにはしない。** exact match→近似探索の順で処理する。

| ステップ | 内容 |
|---|---|
| exact match検索 | AI抽出コード`AU1K430093`で`selected_business_date`=2026-06-26（`SFAエクスポートマスター0626b.xlsx`, `CSV`シート）を検索 → **0件（`not_found`）** |
| 近似探索 | 同シート内の全店舗コードとAI抽出コードの編集距離を計算 → `AU1K4330093`（10行目）が編集距離1（連続する「3」の1桁欠落）で`near_match_candidates`に該当 |
| `csv_match_status` | `not_found`（exact matchが0件のため） |
| `near_match_candidates` | 1件：`source_file=SFAエクスポートマスター0626b.xlsx`, `sheet_name=CSV`, `row_number=10`, `store_code=AU1K4330093`, `edit_distance=1`, `difference_description="連続する3の1桁欠落候補"`, `intro_total=1`, `voice_callout_total=0` |
| `resolved_csv_value` | **null**（近似一致のみで自動確定しない） |
| `review_required` | `true` |
| 備考 | 将大さんの人間入力（`4330093`）は近似候補の店舗コードと一致するが、**この一致を根拠に自動確定はしない**。あくまで人手確認の際の参考情報として`near_match_candidates`を提示する |

### P41（広畑）

| 項目 | 値 |
|---|---|
| 参照ファイル | `SFAエクスポートマスター0626b.xlsx` |
| シート名 | `CSV` |
| 行番号 | 15行目 |
| 結合に使用したキー | 店舗コード`AU1KC400079`（human入力値ベース。AIは店舗コードは抽出済み・A3のみ未抽出）＋`selected_business_date`=2026-06-26 |
| 候補行数 | 1件 |
| 一意に決まった根拠 | `unique_match` |
| CSV上の値 | 店舗コード=`AU1KC400079`、紹介総数=2、お声がけ総数=0 |
| 備考 | written_total_value（human=2）と一致。AI未抽出（written_total_value=null）のためAI側との三者一致は成立しない |

### P59（ららぽーとEXPOCITY）

| 項目 | 値 |
|---|---|
| 参照ファイル | `SFAエクスポートマスター0625nn.xlsx` |
| シート名 | `CSV` |
| 行番号 | 5行目 |
| 結合に使用したキー | 店舗コード`AU1K4050055`＋`selected_business_date`=2026-06-25（P49〜P66範囲） |
| 候補行数 | 1件 |
| 一意に決まった根拠 | `unique_match` |
| CSV上の値 | 店舗コード=`AU1K4050055`、紹介総数=0、お声がけ総数=0 |
| 備考 | written_total_value（human=0）と一致。AI候補6とは不一致。tally_observation_status=no_marks_observed（tally_count=null）と合わせ、review_required化の根拠が3系統中2系統（written・csv）そろって human=0側 を支持する形になる |

### P66（守口南寺方、旧帳票）：`reference_match_unverified`の実例（2.4節）

旧帳票は店舗コードが帳票に印字されない。CSV結合に使った情報の生成元を1ステップずつ明記する。

| ステップ | 情報 | 生成元 |
|---|---|---|
| ① | 店舗名「守口南寺方」 | **AI抽出値**（`stage3_full_results.json` P66の`store_name`フィールド。旧帳票は店舗名が印字されているため、AIがページ画像から直接読み取った値） |
| ② | 店舗名→店舗コード変換：「守口南寺方」→`AU1KW740082` | **`入力マスター`シート**（1.2節・8節で「正式マスターと確認できていない」と位置づけたのと同一の参考データ）を参照して解決。**この変換ステップが未確認の参考データに依存するため、③以降の結合結果は`unique_match`に昇格しない** |
| ③ | CSV結合キー | ②で得た`AU1KW740082`＋`selected_business_date`=2026-06-25（P49〜P66範囲） |

| 項目 | 値 |
|---|---|
| 参照ファイル | `SFAエクスポートマスター0625nn.xlsx` |
| シート名 | `CSV` |
| 行番号 | 18行目 |
| 候補行数 | 1件（ただし②が未確認参考データ経由のため`csv_match_status`は`unique_match`にしない） |
| `csv_match_status` | **`reference_match_unverified`** |
| `csv_candidate_rows` | 参考表示のみ：`row_number=18`, `store_code=AU1KW740082`, `intro_total=6`, `voice_callout_total=0` |
| `resolved_csv_value` | **null**（三者一致の算入対象にしない） |
| `resolution_basis` | `"ai_store_name_plus_unverified_reference_master"` |
| `review_required` | `true` |
| 備考 | written_total_value（human=6）はCSV候補の値（6）と数値上は一致するが、**店舗コードの特定自体が未確認の参考データに依存しているため、この一致を三者一致の根拠にはしない**。あくまで参考情報として提示する |

### P23（ニトリモール枚方、multiple_unresolvedの実例）

| 項目 | 値 |
|---|---|
| 参照ファイル | `SFAエクスポートマスター0627b.xlsx` |
| シート名 | `CSV` |
| 行番号 | 26行目・27行目（2件） |
| 結合に使用したキー | 店舗コード`AU1KW740165`＋`selected_business_date`=2026-06-27（P01〜P28範囲） |
| 候補行数 | 2件 |
| 判定 | `multiple_unresolved`（`business_mode`列が存在せずどちらが店頭/イベントか判別不能。1.1節） |
| CSV上の値（両候補） | 26行目：紹介総数=6, お声がけ総数=0／27行目：紹介総数=5, お声がけ総数=0 |
| 備考 | written_total_value（human=5, AI=5）は27行目と一致するが、**この一致を根拠に27行目を選ぶことはしない**（推測選択の禁止）。`resolved_csv_value=null`のまま`review_required=true`とする |

---

## 11. 判定マトリクス

| written_total | tally_count | csv_match_status | resolved_csv_value | 判定 |
|---|---|---|---|---|
| 値あり | `marks_present`・一致 | `unique_match`・一致 | 一致 | `three_way_match`（review_required=false） |
| 値あり | `marks_present`・一致 | `unique_match`・不一致 | 不一致 | `review_required`（reason: csv_mismatch） |
| 値あり | `marks_present`・不一致 | 問わず | 問わず | `review_required`（reason: written_vs_tally_mismatch） |
| 値あり | null（no_marks_observed等） | `unique_match`・一致 | 一致 | `two_way_match`（written×csv。tallyは証拠不足として記録） |
| 値あり | null | `multiple_unresolved` | **null** | `review_required`（reason: csv_multiple_unresolved）。**三者一致とは表示しない** |
| 値あり | null | `not_found` | null | `review_required`（reason: csv_not_found, insufficient_evidence）。`near_match_candidates`があれば参考情報として提示（reason: near_match_available_not_auto_confirmed） |
| 値あり | 問わず | **`reference_match_unverified`** | **null** | `review_required`（reason: csv_reference_unverified）。**数値が一致していても三者一致とは表示しない**（10節P66） |
| null（AI未抽出） | 問わず | `unique_match` | 値あり | `review_required`（reason: ai_not_extracted。CSV値をreview_reasonsに補助情報として記録） |
| null（AI未抽出） | 問わず | `multiple_unresolved`/`not_found`/`reference_match_unverified` | null | `review_required`（reason: ai_not_extracted, no_corroboration） |

**原則：`written_total`・`tally_count`・`resolved_csv_value`の3系統すべてが揃って一致した場合のみ`three_way_match`。`csv_match_status`が`multiple_unresolved`または`reference_match_unverified`の場合は`resolved_csv_value`を必ずnullとし、他の2系統が一致していても三者一致とは表示しない。`near_match_candidates`は参考情報であり、自動確定には使わない。**

---

## 12. 実装順序（確定）

| Step | 内容 |
|---|---|
| **Step 1** | **CSV candidate resolver**：`unique_match` / `multiple_unresolved` / `not_found` / `resolved_by_rule`を判定するロジック（2節）。Vision抽出に依存せず、既存CSVデータのみで先行実装・単体テスト可能 |
| **Step 2** | `intro_evidence` / `voice_evidence` / `store_code_evidence`スキーマの定義（3節） |
| **Step 3** | Visionプロンプトへ`written_total_*`・`tally_*`系フィールドの出力指示を追加（現行プロンプトの「正の字→数字」融合指示の分離を含む） |
| **Step 4** | triple evidence comparison（written/tally/csvの3系統から`evidence_comparison_result`を算出、11節） |
| **Step 5** | review routing（`review_required`/`review_reasons`の確定） |

### 12.1 最初のテスト対象（Step1完了時点で実行可能なものから着手）

| ページ | 検証内容 |
|---|---|
| **P23** | CSV複数行（26/27行目）で`multiple_unresolved`が正しく判定されるか。`resolved_csv_value=null`になり、written側の一致（human=AI=5）だけでは`three_way_match`にならないことを確認（Step1のみで検証可能） |
| **P32** | AI抽出コード`AU1K430093`でexact matchが0件（`not_found`）になり、近似探索で`AU1K4330093`（編集距離1）が`near_match_candidates`に入るか。**近似候補だけで自動確定されないこと**（`resolved_csv_value=null`、`review_required=true`）を確認（Step1＋Step2） |
| **P41** | AI未抽出（written_total=null）でも、human値とCSV（10節の値=2）が一致することを`review_reasons`に記録できるか（Step1のみで検証可能） |
| **P59** | written_total=0（human）、AI候補=6、`tally_observation_status=no_marks_observed`、`tally_count=null`の状態で、CSV=0との比較結果が正しく`review_required`（reason一覧に3系統の状態が漏れなく記録される）になるか（Step1〜Step4） |
| **P66** | 店舗コード解決が`入力マスター`（未確認参考データ）経由であることを理由に、候補行が1件でも`csv_match_status=reference_match_unverified`となり`unique_match`に昇格しないことを確認。`resolved_csv_value=null`、`review_required=true`になるか（Step1＋2.4節の実装確認） |

---

## 13. 未確定事項

1. **モジュールの物理配置**：新規ディレクトリを切るか、`phase6_temp`内で分割するに留めるか。
2. **`business_mode`の判別方法**：CSV列からは判別不能。PDF側の`shop_event_kubun`との突合や、先方への追加確認質問（`PHASE_6_CLIENT_CONFIRMATION_ITEMS.md`で送付予定/送付済みの確認文案）の回答待ち。回答が得られれば`resolved_by_rule`のルール化を検討。
3. **旧帳票の合計欄の実体**：正の字か算用数字か、複数ページでの再確認が必要。
4. **新帳票の店舗コード欄が全51ページで7桁固定か**：6ページのサンプルのみで一般化してよいか。
5. **`入力マスター`シートの信頼性**：正式マスターでないとすれば、8節の「参考照合」レベルで運用を続けるか、正式マスターの提供を先方に依頼するか（P66のような旧帳票の店舗コード解決に直結する）。
6. **「実績0は必ず空欄とする」運用ルールの先方確認**（Phase 6パイロット結論、並行して進める）。
7. **各フィールド別confidenceをプロンプトにどう出力させるか**：現行プロンプトは1項目の`confidence`のみ。

---

## 14. 再提出サマリ

1. **最終スキーマ**：3節（Vision抽出JSON）＋2節（CSV結合結果の構造）
2. **データの生成元**：Vision抽出＝LLM 1回呼び出し／CSV＝`SFAエクスポートマスター*.xlsx`の`CSV`シート（1節・10節、実データ・行番号まで確認済み）
3. **正本と派生値**：5節（`*_evidence.written_total_value`が正本、`intro_total`等は派生プロパティ）
4. **モジュール構成**：9.2節（6モジュール）＋12節（実装順序Step1〜5）
5. **判定マトリクス**：11節（`csv_match_status`の5値：unique_match/multiple_unresolved/not_found/resolved_by_rule/reference_match_unverified を反映） 
6. **テスト一覧**：10節（P32/P41/P59/P66/P23のCSV結合証跡）＋12.1節（最初のテスト対象5件）

未確定事項（13節）は実装を進めながら解消してよいものと、先方回答待ちのもの（2番・6番）に分かれる。

**この段階ではコード・GT・Excel・検証HTML・Gitへの変更は行っていない。**

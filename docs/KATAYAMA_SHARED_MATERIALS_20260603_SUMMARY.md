# 片山様共有資料 取込サマリー（2026-06-03 更新）

## 受領ファイル一覧

| ファイル | 内容 | 受領日 |
|---------|------|--------|
| 店舗名　スタッフ名.xlsx | 代理店コード・店舗名・スタッフ名一覧 | 2026-06-03 |
| 対応表.pdf | FAX帳票項目 × Salesforce CSV列コード対応表 | 2026-06-03 |

---

## 現在の進捗

- `f319185` で ①eo光〜⑥NURO光 の声掛側コードは反映済み
- 片山様への残件は `docs/katayama_confirmation_items_20260603.csv` に整理済み
- 送付用文面は `docs/katayama_confirmation_message_20260603.md` に作成済み
- 照合ロジック実装は未着手
- `reconciliation.py` / `app.py` は引き続き凍結

---

## マスタ状況

### 1. 店舗コードマスタ

**ファイル**: `data/master/store_code_mapping.csv`

| 項目 | 値 |
|------|-----|
| 件数 | 24件 |
| store_code 形式 | AU1K...（例：AU1KW740165） |
| CSV col 281「法人・店舗(取扱コード)」と一致 | 確認済み |
| 重複 | なし |

### 2. スタッフ名マスタ

**ファイル**: `data/master/staff_name_master.csv`

| 項目 | 値 |
|------|-----|
| 件数 | 28名 |
| 店舗割当あり（Excel同行） | 24名 |
| 店舗未割当（スポット/フローティング） | 4名（新田裕幸、古賀正翔、高橋英威、原田愛香） |
| is_store_assignment_confirmed | 全行 false |
| 重複 | なし |

**補足**: `excel_row_store_code` / `excel_row_store_name` は「Excelの同じ行に並んでいた」参考情報であり、所属店舗の確定データではない。片山様電話確認済みとして、スタッフは店舗固定ではなくスポット入店あり。

### 3. PDF項目 × CSV列対応マスタ

**ファイル**: `data/master/pdf_csv_field_mapping.csv`

| 項目 | 値 |
|------|-----|
| 総行数 | 145行 |
| mapping_status=confirmed | 126行 |
| mapping_status=uncertain | 16行 |
| mapping_status=unreadable | 0行 |
| needs_confirmation=true | 16行（生行集計） |

**進捗メモ**:
- 直近コミット `f319185` にて、①eo光〜⑥NURO光の声掛側コードを確認反映
- 前回 33 件あった確認待ちは、片山様確認用CSVでは 15 項目に整理済み
- 現行CSVの生行集計では `needs_confirmation=true` が 16 行あり、うち 1 行は `既存対応28（コースアップ⇒5G+10G）` のような空欄列が多い特殊行
- `mapping_status=confirmed` の行も、名称不一致メモ（みやブル / おうちの環境保険）は残している

---

## クロダ問題

### 確認結果

`data/master/staff_name_master.csv` の28名を確認した結果、**「クロダ」「黒田」「くろだ」は存在しない**。

### 片山様に確認したいこと

- 帳票上の「クロダ」に該当するスタッフ様が一覧外かどうか
- 正式表記 / カナ表記 / 所属情報
- スポットスタッフや略称運用があるかどうか

---

## 片山様確認用CSVのカテゴリ内訳

| category | 件数 | 内容 |
|---------|------|------|
| A | 5 | ⑦CATV以降の声掛側列コード確認 |
| B | 1 | コースアップ⇒5G+10G のCSV列確認 |
| C | 2 | 名称不一致（みやブル等） |
| D | 1 | クロダ問題 |
| E | 6 | その他、CSV列対応が不明な項目 |

**確認票ファイル**: `docs/katayama_confirmation_items_20260603.csv`

---

## 実装ステータス

| 項目 | 状態 |
|------|------|
| 店舗コードマスタ | 作成完了 |
| スタッフ名マスタ | 作成完了 |
| PDF×CSV列対応マスタ | 確認用マスタとして作成済み |
| 片山様確認票 | 作成完了 |
| 片山様送付文面 | 作成完了 |
| reconciliation.py | 変更なし（凍結中） |
| app.py | 変更なし（凍結中） |
| 照合ロジック実装 | 未着手 |

---

## 次のステップ

1. `docs/katayama_confirmation_message_20260603.md` の内容で片山様へ確認依頼
2. 回答後に `data/master/pdf_csv_field_mapping.csv` を更新
3. 列対応が確定した範囲から照合ロジック設計へ移行

---

**更新日**: 2026-06-03
**作成者**: Claude
**ステータス**: 片山様確認待ち

# 帳票読取・確認画面（試作版）

FAX由来の帳票データから必要項目を抽出し、人が確認・修正できるMVPアプリケーション

## 🎯 目的

- **対象**: ①の手書き書類（1種類）
- **機能**: PDFアップロード → 項目自動抽出 → 手修正 → CSV出力
- **スタンス**: 完全自動化ではなく、人確認前提の半自動化MVP

## 📋 必須機能

- ✅ PDFアップロード
- ✅ 帳票プレビュー表示（左側）
- ✅ 6項目の自動抽出（Claude Vision API）
- ✅ 抽出結果フォーム表示・編集（右側）
- ✅ CSVで出力
- ✅ 初見で「帳票確認画面」と理解できるUI

## 🛠️ セットアップ

### 1. 環境準備

```bash
# Python 3.8+ が必要です
python3 --version

# 仮想環境作成
python3 -m venv venv

# 仮想環境激活
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 2. 依存ライブラリインストール

```bash
pip install -r requirements.txt
```

### 3. Claude API キー設定

```bash
# .env ファイルを作成
cp .env.example .env

# エディタで .env を開き、Claude API キーを設定
# CLAUDE_API_KEY=sk-ant-...your-key-here...
```

**Claude API キーの取得方法:**
- https://console.anthropic.com にアクセス
- API Keys セクションで新しいキーを生成
- `.env` ファイルに貼り付け

### 4. アプリケーション起動

```bash
streamlit run app.py
```

ブラウザが自動的に開き、`http://localhost:8501` でアプリが起動します。

## 📖 使い方

### 基本フロー

1. **帳票ファイルをアップロード**
   - PDFファイルを選択
   - ファイルが読み込まれると、左側にプレビューが表示されます

2. **帳票を解析**
   - 「帳票を解析」ボタンをクリック
   - Claude Vision APIが6つの項目を自動抽出します
   - 結果が右側のフォームに表示されます

3. **内容確認・修正**
   - 原本と照らし合わせて確認
   - 誤りがあれば修正
   - 項目が不足していれば追加

4. **出力**
   - 「保存する」: JSON形式で outputs/ に保存
   - 「CSVで出力」: CSV形式で outputs/ に出力
   - 「CSVをダウンロード」: ブラウザから直接ダウンロード

### 抽出項目

```
1. 処理日          (日付: YYYY-MM-DD)
2. 店舗名          (文字列)
3. 担当者名        (文字列)
4. 件数            (数値)
5. 合計値          (数値)
6. 備考            (テキスト、省略可)
```

## 📂 ファイル構成

```
geo-mvp/
├── app.py                    # Streamlit メインアプリ
├── extractor.py              # Claude Vision API 連携
├── requirements.txt          # 依存ライブラリ
├── .env.example              # 環境変数テンプレート
├── README.md                 # このファイル
├── outputs/                  # 出力ファイル格納先
│   └── result_*.csv          # 出力ファイル
└── uploads/                  # 一時ファイル格納
```

## 🔧 トラブルシューティング

### エラー: `CLAUDE_API_KEY not found`

→ `.env` ファイルを確認し、Claude API キーが正しく設定されているか確認してください

### エラー: `Failed to parse PDF`

→ PDFファイルが破損していないか確認してください。テスト用PDFで試してください

### エラー: `Failed to extract items`

→ 帳票の品質が低い可能性があります。以下を確認してください:
- PDFが鮮明か
- 帳票が正しい向きか
- 項目が帳票に存在するか

### CSVが文字化けする

→ ファイルをExcelで開く際、エンコーディングを UTF-8 に指定してください

## 📊 出力フォーマット

### CSV 出力例

```
処理日,店舗名,担当者名,件数,合計値,備考
2026-05-05,渋谷店,山田太郎,15,353,在庫不足のため一部後日納品
```

### JSON 出力例

```json
{
  "timestamp": "2026-05-05T10:30:00",
  "filename": "sample.pdf",
  "data": {
    "処理日": "2026-05-05",
    "店舗名": "渋谷店",
    "担当者名": "山田太郎",
    "件数": 15,
    "合計値": 353,
    "備考": "在庫不足のため一部後日納品"
  }
}
```

## 🚀 今後の拡張ポイント

### Phase 2 候補

- [ ] **複数帳票対応** - 複数の帳票フォーマットに対応
- [ ] **CSV自動照合** - Salesforce/Excel と自動比較
- [ ] **確認ステータス管理** - 処理状況をトラッキング
- [ ] **Salesforce連携** - 自動入力候補の生成
- [ ] **メール送信** - 確認完了後の自動送信

### 技術的な改善候補

- [ ] **精度改善** - 複数のOCR方式を組み合わせ（ハイブリッド）
- [ ] **ローカルOCR** - Claude API の従課金削減（Tesseract等）
- [ ] **VPS展開** - さくらVPSでの運用
- [ ] **認証機能** - ログイン・権限管理
- [ ] **ログ管理** - 処理履歴の保存

## ⚠️ 注意事項

- **本番品質ではありません**: 試作版（MVP）です。本番運用には別途要件定義が必要です
- **AI精度**: 100%ではありません。必ず原本と照らして確認してください
- **API利用料**: Claude API の従課金が発生します（テスト時は月数百円～数千円程度）
- **個人情報**: PDFにスタッフの個人情報が含まれている場合は、慎重に取り扱ってください

## 🔐 Git セキュリティルール（重要）

このプロジェクトでは、秘密情報の漏洩を防ぐため、以下のルールを **必ず守ってください**。

### コミット時のルール

```bash
# ❌ 禁止: git add . （全ファイル一括追加）
git add .

# ✅ 推奨: ファイル単位で指定
git add app.py extractor.py reconciliation.py README.md .gitignore .env.example
```

### コミット前の必須確認

```bash
# 1. Git ステータス確認
git status

# 2. ステージング内容確認
git diff --cached --name-only

# 3. .env が追跡されていないことを確認
git ls-files .env
# 期待: 何も表示されない

# 4. 秘密情報が含まれていないことを確認
git log --oneline -5
git status
```

### 絶対にコミットしてはいけないもの

- ❌ `.env` （実APIキー）
- ❌ APIキー、トークン（`sk-ant-...` など）
- ❌ 実顧客データ（実FAX帳票PDF、実Salesforce CSV）
- ❌ 読み取り結果CSV（実データ）
- ❌ `__pycache__/` （Python キャッシュ）
- ❌ `*.pyc` （コンパイルファイル）
- ❌ 一時ファイル（`*.tmp`, `*.temp` など）

### .gitignore 設定（確認事項）

```gitignore
# Environment variables
.env
.env.*
!.env.example

# Python cache
__pycache__/
*.pyc
*.pyo

# Real customer data
real_*.pdf
real_*.csv
/outputs/real_*
```

### 過去のミス事例

**2026-05-09**: `.env` ファイルが Git 履歴に含まれました
- 原因: コミット前の�キュリティ確認が不足
- 対応: git filter-repo で履歴から削除、API Key を無効化・再発行
- 教訓: `git add .` を使わず、ファイル単位で指定すること

---

## 📞 サポート

このアプリケーションについて質問がある場合は、お気軽にお問い合わせください。

---

**作成日**: 2026-05-05  
**バージョン**: 0.1.0 (MVP)  
**ステータス**: 試作版  
**最終更新**: 2026-05-09 （Git セキュリティルール追記）

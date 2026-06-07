# Phase 6B AI Tally V2 - Vision API テスト実行計画書

**作成日：** 2026-06-07  
**対象：** P14, P11, P24, P12, P28 (5ページ)  
**目的：** 改善プロンプートの実Vision APIテスト実施

---

## 🚀 実行方法（3つのオプション）

### オプション1：ローカルWindows環境 ⭐ 推奨

```powershell
# PowerShell で実行

# 1. ライブラリをインストール
pip install anthropic PyMuPDF Pillow

# 2. APIキーを設定（あなたのキーに置き換え）
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 3. プロジェクトディレクトリに移動
cd "C:\Users\maris\Desktop\Claude 作業\geo-mvp"

# 4. テストスクリプトを実行
python scripts/test_ai_tally_prompt_v2_actual.py
```

**実行時間：** 5-10分  
**場所：** C:\Users\maris\Downloads\20260529130020168.pdf （正本PDF）  
**出力：**
- `data/test_outputs/phase6b_ai_tally_prompt_v2_actual_result.csv`
- `docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md`

---

### オプション2：Google Colab（インターネット接続のみ）

```python
# Colab notebook で実行

# セットアップ
!pip install anthropic PyMuPDF Pillow
!git clone https://github.com/your-repo/geo-mvp.git
%cd geo-mvp

# PDFをアップロード
from google.colab import files
uploaded = files.upload()  # 20260529130020168.pdf をアップロード

# スクリプト実行
!python scripts/test_ai_tally_prompt_v2_actual.py
```

**利点：** インターネット接続環境があれば即実行可能  
**制約：** PDFをアップロードする手間

---

### オプション3：macOS/Linux環境

```bash
# Terminal で実行

# 1. ライブラリをインストール
pip install anthropic PyMuPDF Pillow

# 2. APIキーを設定
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. プロジェクトディレクトリに移動
cd ~/your-path/geo-mvp

# 4. テストスクリプトを実行
python scripts/test_ai_tally_prompt_v2_actual.py
```

---

## 📊 テスト内容の概要

### テスト対象（5ページのみ）

| # | ページ | 店舗名 | v3値 | 期待値 | 改善内容 |
|---|--------|--------|------|--------|---------|
| 1 | P14 | イオンモール神戸北 | 34 | → 3 | 正の字（3画）の正確判定 |
| 2 | P11 | 深江橋 | 20 | → 2 | 正の字（2画）の正確判定 |
| 3 | P24 | 六甲道 | 7 | → 2 | 正の字（2画）の正確判定 |
| 4 | P12 | 広畑 | 0 | → 1 | 正の字（1画）の正確判定 |
| 5 | P28 | 宝殿 | 0 | → 0 | 空欄の維持 |

### スクリプトの処理フロー

```
PDFを読み込む
  ↓
5ページを順番に処理：
  1. P14 (page_index=13)
     - ページをPNG画像として抽出
     - AI欄をcrop
     - Vision APIに改善プロンプトで送信
     - 結果を正規化・保存
     ↓
  2. P11 (page_index=10)
     - 同様の処理
     ↓
  3. P24 (page_index=23)
     - 同様の処理
     ↓
  4. P12 (page_index=11)
     - 同様の処理
     ↓
  5. P28 (page_index=27)
     - 同様の処理
  ↓
結果をCSVとMarkdownで出力
  ↓
コンソールにサマリーを表示
```

---

## ✅ テスト実行の期待結果

### 成功時（期待）

```
成功率：5/5 = 100%

P14: v3=34 → Vision V2実測値=3 → ユーザー目視=3 ✅
P11: v3=20 → Vision V2実測値=2 → ユーザー目視=2 ✅
P24: v3=7  → Vision V2実測値=2 → ユーザー目視=2 ✅
P12: v3=0  → Vision V2実測値=1 → ユーザー目視=1 ✅
P28: v3=0  → Vision V2実測値=0 → ユーザー目視=0 ✅

34/20/7の誤読が完全に消える ✅
P28=0を維持 ✅

次ステップ：全30ページへ展開
```

### 部分成功時（期待とは異なる場合）

```
成功率：4/5 = 80%

例）P12だけ失敗した場合：
P12: v3=0 → Vision V2実測値=0 → ユーザー目視=1 ❌

原因分析：
- Vision APIが「blank」を「0」と解釈した可能性
- クロップ領域にテンプレート線が含まれた可能性

対応：
- プロンプトを改良して再テスト
```

---

## 📝 実行後の手順

### ステップ1：結果ファイルの確認

```bash
# 生成されたファイルを確認
ls data/test_outputs/phase6b_ai_tally_prompt_v2_actual_result.csv
ls docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md

# CSVの内容を確認
cat data/test_outputs/phase6b_ai_tally_prompt_v2_actual_result.csv

# Markdownレポートを確認（テキストエディタで開く）
cat docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md
```

### ステップ2：成功基準の確認

```
チェック項目：

□ 5ページ中4ページ以上正解？
  → CSVの「match_user」列で「✓」の数をカウント

□ P28=0を維持？
  → P28の「v2_actual_value」が「0」か確認

□ 34/20/7の誤読が消えた？
  → P14: v2_actual_value ≠ 34
  → P11: v2_actual_value ≠ 20
  → P24: v2_actual_value ≠ 7

□ null/uncertainに逃げていない？
  → v2_actual_value が null や「uncertain」でない確認
```

### ステップ3：git コミット

```bash
# ファイルをステージング（git add . は使わない）
git add data/test_outputs/phase6b_ai_tally_prompt_v2_actual_result.csv
git add docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md

# コミット
git commit -m "test: run actual AI tally prompt v2 on five pages"

# ログで確認
git log --oneline -1
```

---

## 🎯 次フェーズへの判定基準

### 成功した場合（4/5以上）

```
✅ 判定：全30ページへ展開可能

次のアクション：
1. extractor.py に改善プロンプトを反映
2. 全30ページで再抽出実施
3. AI FLAG 13件の削減効果を検証
4. 自動確定率 60% → 70% 向上確認
```

### 失敗した場合（3/5以下）

```
❌ 判定：改善が必要

次のアクション：
1. 失敗したページの Vision 出力を詳細分析
2. クロップ位置の調整
3. プロンプトの改良
4. テスト再実行
```

---

## 🔧 よくあるトラブル

### エラー1：「ANTHROPIC_API_KEY not set」

```
原因：APIキーが設定されていない

対処方法：
PowerShell：
  $env:ANTHROPIC_API_KEY = "sk-ant-..."
  
Bash/Zsh：
  export ANTHROPIC_API_KEY="sk-ant-..."

確認：
  echo $env:ANTHROPIC_API_KEY  (PowerShell)
  echo $ANTHROPIC_API_KEY      (Bash)
```

### エラー2：「PDF not found」

```
原因：正本PDFが見つからない

対処方法：
  C:\Users\maris\Downloads\20260529130020168.pdf
  が存在することを確認

PowerShell確認：
  ls "C:\Users\maris\Downloads\20260529130020168.pdf"
```

### エラー3：「Module not found: anthropic」

```
原因：ライブラリがインストールされていない

対処方法：
  pip install anthropic PyMuPDF Pillow
  
確認：
  pip list | grep -E "anthropic|PyMuPDF|Pillow"
```

### エラー4：「Vision API rate limit」

```
原因：API呼び出しレート制限に引っかかった

対処方法：
  - 5ページのテストなので制限に引っかかることはまれ
  - 数分待ってから再実行
  - 本番環境では1ページずつ処理
```

---

## 📞 詳細なガイド

詳細な手順については、以下のファイルを参照してください：

```
docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_TEST_GUIDE.md
  → 詳細な実行手順
  → トラブルシューティング
  → FAQ
```

---

## 📦 提供ファイル一覧

```
【テスト実行用】
  scripts/test_ai_tally_prompt_v2_actual.py
    → 5ページのVision APIテストスクリプト
    → CSV + Markdownレポート出力

  data/test_outputs/improved_ai_prompt_v2.txt
    → Vision API用改善プロンプト
    → 正の字ルール明確化版

【ガイド・ドキュメント】
  docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_TEST_GUIDE.md
    → 詳細な実行手順

  docs/PHASE_6B_AI_TALLY_V2_TEST_STATUS.md
    → 現在の状態・準備完了事項

  VISION_API_TEST_EXECUTION_PLAN.md
    → このファイル（実行計画書）
```

---

## ⏰ 予想スケジュール

```
現在：2026-06-07 テスト準備完了

実行：今日中（ユーザー環境）
  → 5-10分で完了

検証：実行直後
  → 成功基準チェック
  → 結果確認

コミット：検証後
  → git add / git commit

判定：コミット後
  → 全30ページへ展開判定
```

---

## 📌 重要事項

```
【実行者向け】
  ✓ これは理論的期待値ではなく、実Vision APIテスト
  ✓ 実際のVision API呼び出しが必要
  ✓ インターネット接続が必須
  ✓ API呼び出し費用は約$0.015（ほぼ無視可能）

【確認すべき項目】
  ✓ 5ページすべてが処理されたか
  ✓ エラーがないか
  ✓ 成功基準を満たしているか
  ✓ 誤読が本当に消えたか

【注意事項】
  ✓ 全30ページへは進まない（検証テストのみ）
  ✓ 実測値が期待値と異なる可能性あり
  ✓ その場合は詳細分析・改善が必要
```

---

## ✨ 最終確認

実行前チェックリスト：

```
準備：
  □ 正本PDF: C:\Users\maris\Downloads\20260529130020168.pdf 存在
  □ ANTHROPIC_API_KEY: 有効なAPIキー設定済み
  □ Python: 3.8以上インストール済み
  □ ライブラリ: anthropic, PyMuPDF, Pillow インストール済み
  □ インターネット: 接続確認済み

実行：
  □ scripts/test_ai_tally_prompt_v2_actual.py 実行
  □ 5ページが順番に処理される
  □ Vision APIが正常に呼び出される
  □ エラーが発生しない

検証：
  □ phase6b_ai_tally_prompt_v2_actual_result.csv 生成確認
  □ PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md 生成確認
  □ 成功基準チェック（4/5以上？）
  □ 誤読消滅確認（34/20/7？）

コミット：
  □ git add（両ファイル指定）
  □ git commit（メッセージ記載）
  □ git log で確認
```

---

**テスト実行：** 準備完了  
**次のアクション：** ユーザーが上記いずれかのオプションでスクリプトを実行  
**所要時間：** 5-10分  
**期待結果：** 5/5成功 = 全30ページへ展開可能

**注：** このプランをユーザーが実行完료後、結果をコミットしていただければ、
全30ページ展開への最終判定をさせていただきます。

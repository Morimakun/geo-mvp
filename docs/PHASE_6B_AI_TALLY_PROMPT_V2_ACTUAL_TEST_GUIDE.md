# Phase 6B AI Tally Prompt V2 - 実Vision APIテスト 実行ガイド

**作成日：** 2026-06-07  
**目的：** 改善プロンプントを使用した実Vision APIテストの実行方法を提供

---

## ⚠️ 重要：環境制約について

現在のClaudeコードエディタ環境では、Pythonスクリプトの直接実行に制約があります。
以下の手順で、ローカル環境またはGoogle Colabでテストを実行してください。

---

## 1. 準備事項

### 1.1 必須ファイル

以下のファイルが準備済みです：

1. **テストスクリプト**
   - `scripts/test_ai_tally_prompt_v2_actual.py`
   - 目的：5ページのAI欄をVision APIで読み取る

2. **改善プロンプント**
   - `data/test_outputs/improved_ai_prompt_v2.txt`
   - 正の字ルール明確化版

3. **テスト定義**
   - P14（page_index=13）イオンモール神戸北
   - P11（page_index=10）深江橋
   - P24（page_index=23）六甲道
   - P12（page_index=11）広畑
   - P28（page_index=27）宝殿

### 1.2 正本PDF

```
場所：C:\Users\maris\Downloads\20260529130020168.pdf
ファイルサイズ：3.1 MB
ページ数：30ページ以上
```

### 1.3 APIキー

```
環境変数：ANTHROPIC_API_KEY
取得元：https://console.anthropic.com/
```

---

## 2. ローカル環境での実行（推奨）

### 2.1 必須ライブラリのインストール

```bash
pip install anthropic PyMuPDF Pillow
```

### 2.2 スクリプトの実行

#### Windows (PowerShell)

```powershell
# 1. APIキーを設定
$env:ANTHROPIC_API_KEY = "sk-ant-..."  # あなたのキーに置き換え

# 2. プロジェクトディレクトリに移動
cd "C:\Users\maris\Desktop\Claude 作業\geo-mvp"

# 3. スクリプト実行
python scripts/test_ai_tally_prompt_v2_actual.py
```

#### macOS / Linux

```bash
# 1. APIキーを設定
export ANTHROPIC_API_KEY="sk-ant-..."  # あなたのキーに置き換え

# 2. プロジェクトディレクトリに移動
cd ~/your-path/geo-mvp

# 3. スクリプト実行
python scripts/test_ai_tally_prompt_v2_actual.py
```

### 2.3 実行時間

```
予想実行時間：5-10分
- PDF処理：1-2分
- Vision API呼び出し：3-5分（ネットワーク遅延含む）
- 結果出力：1-2分
```

---

## 3. Google Colabでの実行

Google Colabを使用する場合、以下の手順でテストを実行できます：

### 3.1 セットアップ

```python
# 1. リポジトリをクローン
!git clone https://github.com/your-repo/geo-mvp.git
%cd geo-mvp

# 2. ライブラリをインストール
!pip install anthropic PyMuPDF Pillow

# 3. APIキーを設定
import os
os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-...'  # あなたのキーに置き換え
```

### 3.2 実行

```python
# PDFをアップロード（Colabの場合）
from google.colab import files
uploaded = files.upload()  # 20260529130020168.pdf をアップロード

# スクリプト実行
!python scripts/test_ai_tally_prompt_v2_actual.py
```

---

## 4. テスト実行時の確認事項

### 4.1 期待される出力

スクリプト実行時に以下の出力が表示されます：

```
==========================================
Phase 6B AI Tally Prompt V2 - 実Vision APIテスト
==========================================

✓ PDF found: 20260529130020168.pdf
✓ Improved prompt loaded from: data/test_outputs/improved_ai_prompt_v2.txt
✓ Anthropic client initialized

==========================================
Vision API テスト実行中...
==========================================

【P14】イオンモール神戸北
  page_index=13, v3=34, user_interpretation=3
  → Extracting page from PDF... ✓
  → Cropping AI area... ✓ (xxx x yyy)
  → Encoding image... ✓
  → Calling Vision API... ✓
  → Vision value: 3 ✅
  → Interpretation: format_b
  → Confidence: high
  → Expected: 3 (user interpretation)

...（P11, P24, P12, P28 も同様）...
```

### 4.2 出力ファイル

スクリプト成功時、以下のファイルが生成されます：

```
data/test_outputs/phase6b_ai_tally_prompt_v2_actual_result.csv
docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md
```

---

## 5. テスト結果の評価

### 5.1 成功基準

```
✅ 成功：以下を全て満たす場合
  - 5ページ中 4ページ以上が正解
  - P28 = 0 を維持
  - 34/20/7 の誤読が消える
  - null/uncertain に逃げていない

⚠️  部分成功：以下の場合
  - 5ページ中 3ページ正解
  - 誤読は消えたが値が異なる

❌ 失敗：以下の場合
  - 5ページ中 2ページ以下
  - 誤読が残存
```

### 5.2 期待される結果

```
【改善前（v3値）】
P14: 34 ❌
P11: 20 ❌
P24: 7 ❌
P12: 0 ❌
P28: 0 ✅

正解率：1/5 = 20%

【改善後（期待値）】
P14: 34 → 3 ✅
P11: 20 → 2 ✅
P24: 7 → 2 ✅
P12: 0 → 1 ✅
P28: 0 ✅

期待正解率：5/5 = 100%
```

---

## 6. トラブルシューティング

### 6.1 エラー：「ANTHROPIC_API_KEY not set」

```
解決策：
  1. APIキーが設定されているか確認
  2. キーの形式：sk-ant-... で始まっているか確認
  3. 環境変数が正しく設定されているか確認
  
PowerShell:
  $env:ANTHROPIC_API_KEY = "your-key"
  
Bash/Zsh:
  export ANTHROPIC_API_KEY="your-key"
```

### 6.2 エラー：「PDF not found」

```
解決策：
  正本PDF: C:\Users\maris\Downloads\20260529130020168.pdf
  が存在することを確認してください
  
PowerShell:
  ls "C:\Users\maris\Downloads\20260529130020168.pdf"
```

### 6.3 エラー：「Module not found」

```
解決策：
  pip install anthropic PyMuPDF Pillow
  
確認：
  pip list | grep -E "anthropic|PyMuPDF|Pillow"
```

### 6.4 エラー：「Vision API rate limit」

```
解決策：
  - 5ページのテストなので制限に引っかかる可能性は低い
  - 数分待ってから再試行
  - 本番環境では1ページずつ処理
```

---

## 7. 結果を共有する場合

テスト実行後、以下のファイルをコミットしてください：

```bash
git add data/test_outputs/phase6b_ai_tally_prompt_v2_actual_result.csv
git add docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md
git commit -m "test: run actual AI tally prompt v2 on five pages"
```

---

## 8. 次のステップ

### テストが成功した場合（4/5以上）

1. **結果を確認**
   - `PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md` を確認

2. **成功基準チェック**
   - 34/20/7 誤読が消えたか
   - P28=0 を維持したか

3. **全30ページへ進む**
   - `extractor.py` に改善プロンプトを反映
   - 全30ページで再抽出
   - AI FLAG 13件の削減効果を検証

### テストが失敗した場合（3/5以下）

1. **原因分析**
   - Vision の出力を詳細に確認
   - クロップ位置に問題がないか
   - プロンプートの改良が必要か

2. **改善**
   - `improved_ai_prompt_v2.txt` を修正
   - テストスクリプトを再実行

3. **再テスト**
   - 同じ5ページでテスト
   - 成功基準達成を確認

---

## 9. テストスクリプトの詳細

### スクリプトの流れ

```
1. PDF読み込み
   ↓
2. 5ページを順番に処理
   ├─ P14 (page_index=13)
   ├─ P11 (page_index=10)
   ├─ P24 (page_index=23)
   ├─ P12 (page_index=11)
   └─ P28 (page_index=27)
   ↓
3. 各ページで以下を実行
   ├─ PDFページを画像として抽出（2xズーム）
   ├─ AI欄をcrop
   ├─ Base64エンコード
   ├─ Vision APIに改善プロンプで送信
   └─ 結果を正規化
   ↓
4. 結果をCSVとMarkdownで出力
   ↓
5. サマリーを表示
```

### パラメータ

```python
# クロップ座標（ページ内の相対位置）
left: 35% (AI列の開始)
top: 55% (AI行の開始)
right: 50% (AI列の終了)
bottom: 70% (AI行の終了)
```

---

## 10. よくある質問

### Q1: なぜ5ページだけのテストなのか？

A: 全30ページへ進める前に、改善プロンプトの効果を検証するため。
  成功確認後に全30ページで再抽出を実施します。

### Q2: Vision API のコストはいくら？

A: クラウドビジョン API 呼び出しのコスト：
  - 1つの画像読取 = 約 $0.003
  - 5ページ = 約 $0.015（ほぼ無視できる額）

### Q3: 実行結果を別のマシンで共有できるか？

A: はい。出力ファイルをコミット・プッシュして他のマシンで確認可能：
  ```bash
  git push origin main
  # 別マシンで
  git pull origin main
  ```

### Q4: プロンプトを改良したい場合は？

A: `improved_ai_prompt_v2.txt` を編集して再実行：
  ```bash
  # プロンプートを編集
  vi data/test_outputs/improved_ai_prompt_v2.txt
  
  # テスト再実行
  python scripts/test_ai_tally_prompt_v2_actual.py
  ```

---

**このガイドに従って実Vision APIテストを実行してください。**

**テスト完了後、以下の情報と共に報告してください：**
- ✅ 実Vision APIテスト結果
- v3値 → V2実測値 → ユーザー目視解釈値
- 正解数
- 34/20/7誤読が消えたか
- P28=0を維持できたか
- 全30ページへ進むべきか
- 変更ファイル
- コミットID

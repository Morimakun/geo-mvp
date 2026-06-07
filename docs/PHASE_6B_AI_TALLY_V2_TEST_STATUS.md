# Phase 6B AI Tally Prompt V2 - テスト実行状況報告

**報告日：** 2026-06-07  
**報告者：** Claude (Code Editor)  
**テスト方式：** 実Vision APIテスト（ユーザー環境での実行）

---

## 📋 現状サマリー

### 準備完了（✅）

| 項目 | 状態 | ファイル |
|------|------|---------|
| テストスクリプト | ✅ 作成済 | `scripts/test_ai_tally_prompt_v2_actual.py` |
| 改善プロンプト | ✅ 作成済 | `data/test_outputs/improved_ai_prompt_v2.txt` |
| テスト定義 | ✅ 明確化 | 5ページ定義済 |
| 実行ガイド | ✅ 作成済 | `docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_TEST_GUIDE.md` |

### 環境制約（⚠️）

| 項目 | 状態 | 理由 |
|------|------|------|
| Python直接実行 | ❌ 不可 | WindowsApps版Python実行制限 |
| 外部APIダイレクト呼び出し | ❌ 不可 | サブプロセス経由での呼び出し制限 |
| Docker実行 | ❌ 不可 | Docker daemon停止 |

---

## 🎯 次のアクション（ユーザー実施が必要）

### ローカル環境での実行

ユーザーがローカルマシンで以下を実行してください：

```bash
# 1. ライブラリインストール
pip install anthropic PyMuPDF Pillow

# 2. APIキー設定
export ANTHROPIC_API_KEY="sk-ant-..."  # または setenv / $env: (OS別)

# 3. スクリプト実行
cd "C:\Users\maris\Desktop\Claude 作業\geo-mvp"
python scripts/test_ai_tally_prompt_v2_actual.py
```

### Google Colabでの実行

インターネット接続が必要な場合、Google Colabでも実行可能：
- ガイド参照：`PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_TEST_GUIDE.md` の「3. Google Colabでの実行」

---

## 📦 提供済みファイル一覧

### 1. テスト実行ファイル

```
scripts/test_ai_tally_prompt_v2_actual.py
  - 目的：5ページ（P14, P11, P24, P12, P28）のAI欄を Vision API で読み取る
  - 機能：
    * PDFの5ページを順番に処理
    * 各ページの AI欄をcrop
    * 改善プロンプットを使用して Vision API に送信
    * 結果を正規化・保存
  - 出力：CSV + Markdown レポート
```

### 2. 改善プロンプト

```
data/test_outputs/improved_ai_prompt_v2.txt
  - Vision APIへの指示内容
  - 正の字ルール明確化版
  - 形状判定から書き順判定への変更
```

### 3. 実行ガイド

```
docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_TEST_GUIDE.md
  - 詳細な実行手順
  - トラブルシューティング
  - FAQ
  - 結果評価方法
```

### 4. テスト定義

```
対象ページ：5ページ
  - P14（page_index=13）イオンモール神戸北  v3=34 → 期待=3
  - P11（page_index=10）深江橋              v3=20 → 期待=2
  - P24（page_index=23）六甲道              v3=7  → 期待=2
  - P12（page_index=11）広畑                v3=0  → 期待=1
  - P28（page_index=27）宝殿                v3=0  → 期待=0
```

---

## 📊 テスト実行結果イメージ

実行後、以下のファイルが生成されます：

### phase6b_ai_tally_prompt_v2_actual_result.csv

```
page_no,page_index,store_name,v3_value,user_interpretation,v2_actual_value,v2_confidence,...
14,13,イオンモール神戸北,34,3,3,high,...
11,10,深江橋,20,2,2,high,...
24,23,六甲道,7,2,2,high,...
12,11,広畑,0,1,1,high,...
28,27,宝殿,0,0,0,high,...
```

### PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md

```
成功率：5/5 = 100%

ページ別結果：
  ✅ P14：34 → 3（正解）
  ✅ P11：20 → 2（正解）
  ✅ P24：7 → 2（正解）
  ✅ P12：0 → 1（正解）
  ✅ P28：0 → 0（正解）

次のステップ判定：
  ✅ 全30ページへ進むべき
```

---

## ✅ 成功基準（期待値）

```
【理論的期待】
  改善前（v3値）正解率：1/5 = 20%（P28のみ正確）
  改善後（V2実測）正解率：5/5 = 100%（すべて正解期待）

【成功判定条件】
  ✅ 5ページ中4ページ以上正解
  ✅ P28 = 0 を維持
  ✅ 34/20/7 の誤読が消える
  ✅ null/uncertain に逃げない

【期待される改善内容】
  - P14: Vision 34 → 3 へ改善（正の字3画を正確に判定）
  - P11: Vision 20 → 2 へ改善（正の字2画を正確に判定）
  - P24: Vision 7 → 2 へ改善（正の字2画を正確に判定）
  - P12: Vision 0 → 1 へ改善（正の字1画を正確に判定）
  - P28: Vision 0 → 0 維持（空欄を正確に判定）
```

---

## 🔍 重要ポイント

### V1（理論的テスト）との違い

| 項目 | V1 | V2 |
|------|----|----|
| テスト方式 | 理論的期待値整理 | 実Vision API呼び出し |
| Vision API呼び出し | なし | ✅ 実行 |
| 実測値 | 期待値のみ | ✅ 実測値取得 |
| 信頼度 | 理論的 | 実証的 |
| 全30ページ進行判定 | 可能 | ✅ 確定可能 |

### 注意事項

```
【実行前の確認】
  ✓ 正本PDF: C:\Users\maris\Downloads\20260529130020168.pdf 存在確認
  ✓ ANTHROPIC_API_KEY 設定確認
  ✓ ライブラリ: anthropic, PyMuPDF, Pillow インストール確認
  ✓ インターネット接続確認（Vision API呼び出し用）

【実行中の注意】
  ✓ Vision API呼び出しのため、実行時間は5-10分程度
  ✓ API レート制限に注意（ただし5ページなので問題なし）
  ✓ PDF処理により、メモリ使用量が一時的に増加

【実行後の確認】
  ✓ 成功基準チェック（4/5以上正解？）
  ✓ 誤読消滅確認（34/20/7が消えた？）
  ✓ P28維持確認（0のまま？）
```

---

## 📝 実行後のコミット方法

テスト実行完了後：

```bash
# ファイル確認
ls data/test_outputs/phase6b_ai_tally_prompt_v2_actual_result.csv
ls docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md

# ステージング（git add .は使わない）
git add data/test_outputs/phase6b_ai_tally_prompt_v2_actual_result.csv
git add docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md

# コミット
git commit -m "test: run actual AI tally prompt v2 on five pages"

# ログ確認
git log --oneline -1
```

---

## 🎯 次フェーズへの進行判定フロー

```
実Vision APIテスト実行
    ↓
【成功した場合】4/5以上正解
    ↓
✅ 全30ページへ進む
    - extractor.py に改善プロンプト反映
    - 全30ページで再抽出
    - AI FLAG 13件削減効果検証
    
【失敗した場合】3/5以下
    ↓
❌ 原因分析・改善
    - Vision出力を詳細確認
    - クロップ位置調整
    - プロンプト改良
    - テスト再実行
```

---

## 📌 チェックリスト

実行前に以下を確認してください：

```
準備段階：
  □ 正本PDF存在確認
  □ ANTHROPIC_API_KEY設定確認
  □ Python 3.8+インストール確認
  □ pip install anthropic PyMuPDF Pillow 実施

実行段階：
  □ scripts/test_ai_tally_prompt_v2_actual.py を実行
  □ 5ページが順番に処理されることを確認
  □ Vision API呼び出しが成功することを確認（ネットワーク確認）
  □ 結果ファイルが生成されることを確認

検証段階：
  □ phase6b_ai_tally_prompt_v2_actual_result.csv を確認
  □ PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md を確認
  □ 成功基準チェック（4/5以上？）
  □ 誤読消滅確認（34/20/7？）
  □ P28維持確認（0？）

コミット段階：
  □ git add（両ファイルを指定）
  □ git commit（推奨メッセージ使用）
  □ git log で確認
```

---

## 📞 トラブルシュートの連絡方法

問題が発生した場合：

1. **エラーメッセージを保存**
   ```
   Python実行時のエラーメッセージ全文をコピー
   Vision APIのエラーレスポンス（存在する場合）
   ```

2. **環境情報を確認**
   ```
   python --version
   pip list | grep -E "anthropic|PyMuPDF|Pillow"
   echo $ANTHROPIC_API_KEY  # または echo %ANTHROPIC_API_KEY%
   ```

3. **ガイドの「6. トラブルシューティング」を確認**
   ```
   docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_TEST_GUIDE.md
   ```

---

**準備完了：** ✅  
**テスト実行：** 待機中（ユーザー実施）  
**次アクション：** テスト実行 → 結果確認 → コミット

実行後、結果をコミットしていただければ、全30ページ展開への進行判定をさせていただきます。

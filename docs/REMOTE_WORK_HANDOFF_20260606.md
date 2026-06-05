# Geo MVP: Remote Work Handoff (2026-06-06)

**最終更新**: 2026-06-06 00:30 JST  
**進捗**: Phase 1-4b 完了、Phase 6B 途中（HI=40 修正済み）

---

## 📊 現在の状態

### フェーズ進捗

| Phase | Status | 備考 |
|-------|--------|------|
| **1-4a** | ✅ 完了 | PDF-CSV照合ロジック実装済み |
| **4b** | ✅ 完了 | Streamlit UIで照合結果表示 |
| **5** | ⏭️ スキップ | DB保存不要（デモ用） |
| **6B** | 🔧 修正中 | PDF領域別抽出：69.2%成功（HI=40修正済み） |

### API状態

- ✅ APIクレジット補充済み（2026-06-06）
- ✅ Vision API 利用可能
- ⚠️ Page 16-29 は前回 400 エラー → 再実行予定

### 検証データ

| 対象 | 内容 | 状態 |
|------|------|------|
| **PDF** | 20260529130020168.pdf（30ページ） | ✅ 完備 |
| **CSV** | report1780043296399.csv（Salesforce） | ✅ 完備 |
| **Master** | store_code_mapping.csv, field_mapping.csv | ✅ 完備 |

---

## 🔗 最新コミット一覧

### 重要コミット（直近）

| ID | 日時 | メッセージ | 内容 |
|----|----|----------|------|
| `e36a381` | 2026-06-06 | verify HI=40 fix after API reload | HI=40 修正検証（16ページ全て成功） |
| `d676a8c` | 2026-06-06 | fix existing_support HI=40 misread | HI=40 修正（bounds調整+prompt強化） |
| `3f310d3` | 2026-06-06 | evaluate phase6b extraction 30pages | 30ページPDF抽出検証（69.2%成功） |

### 参考コミット（Phase 4b）

| ID | メッセージ |
|----|----------|
| `ac4fd08` | implement phase4b ui helpers |
| 以前のcommit | ... |

---

## 🎯 次にやる作業（優先度順）

### **Priority 1: HI=40 修正後の最適化**

**Status**: HI=40 は消えたが、HH/HJ が null に増加  
**Issue**: bounds (12,22,75,100) が右に寄りすぎた（テンプレート値が見える）

**アクション**:
1. bounds を (12,22,70,100) または (12,22,65,100) に調整
2. Page 0-15 で再実行
3. HH/HJ/HI の値が改善したか確認
4. CSV と MD レポートを生成

**コマンド**:
```bash
# evaluate_phase6b_30pages.py の REGIONS['existing_support']['bounds'] を修正
# または、新規スクリプトを作成
python scripts/optimize_existing_support_bounds.py
```

**成功基準**:
- HI=40 が出ない（維持）
- HH/HJ/HI が合理的な値を返す
- null 率が < 80%

---

### **Priority 2: new_options 領域の修正**

**Status**: 全ページ 0% 成功率（全項目 null）  
**Issue**: bounds (18,50,38,62) が新規オプション欄にうまく合っていない

**アクション**:
1. Page 0-15 の new_options crop 画像を確認
2. 手書き値が実在するページを特定
3. bounds を調整（上下・左右両方の可能性）
4. zoom を 3 または 2 に下げて試す
5. Page 0-15 で再実行

**参考ファイル**:
```
data/test_outputs/phase6b_diagnosis/  # 既存crop画像
data/test_outputs/visual_inspection/  # new_options crop
```

**コマンド**:
```bash
python scripts/diagnose_new_options_bounds.py
python scripts/optimize_new_options_bounds.py
```

---

### **Priority 3: Page 16-29 の再実行**

**Status**: 前回API 400エラーで未処理（14ページ）  
**Now**: APIクレジット補充済みなので再実行可能

**アクション**:
1. evaluate_phase6b_30pages.py を実行
2. Page 0-15 の結果も一緒に取得（修正版bounds適用）
3. 30ページ全体の统计を更新
4. new_options の 0% を改善できたか確認

**コマンド**:
```bash
python scripts/evaluate_phase6b_30pages.py  # 修正版で全30ページ実行
```

---

### **Priority 4: Phase 1-4b への再投入**

**Status**: 修正後の existing_support, new_options を照合エンジンに投入

**条件**:
- existing_support: HI=40 なし、HH/HJ/HI が妥当な値
- new_options: GS/GT/GU が 30% 以上成功
- case_items: 現状維持（72.5%）

**アクション**:
1. 修正済み抽出結果を使って Phase 1-4a を再実行
2. store_code 変換成功率、CSV候補絞り込み、field比較を再検証
3. 不一致が減ったか確認
4. Phase 4b UI で表示

**コマンド**:
```bash
python scripts/validate_real_30pages_reconciliation.py  # 修正結果で再検証
```

---

## 💻 実行コマンド（クイックリファレンス）

### テスト・検証

```bash
# 全テスト実行
python -m pytest tests/ -v

# Phase 4b UI テスト
python scripts/test_phase4b_ui.py

# Phase 6B 30ページ検証（修正版）
python scripts/evaluate_phase6b_30pages.py
```

### Phase 6B 最適化（次にやる）

```bash
# existing_support HI=40 修正の検証
python scripts/verify_hi40_fix.py

# HI=40 修正後の bounds 最適化
python scripts/optimize_existing_support_bounds.py  # 未作成（作成必要）

# new_options 診断
python scripts/diagnose_new_options_bounds.py  # 未作成（作成必要）

# new_options 修正
python scripts/optimize_new_options_bounds.py  # 未作成（作成必要）
```

### Phase 1-4b 再投入テスト

```bash
# 修正結果を使った照合精度再検証
python scripts/validate_real_30pages_reconciliation.py
```

### コミット・管理

```bash
# ステータス確認
git status

# ログ確認（最新10件）
git log --oneline -10

# 修正後の変更をステージ（git add . は禁止）
git add scripts/optimize_existing_support_bounds.py docs/PHASE_6B_*.md data/test_outputs/phase6b_*.csv
git commit -m "test: optimize existing_support bounds after HI=40 fix"
```

---

## 📁 ファイル構成

### 触ってよい（安全）

```
scripts/
  ├── evaluate_phase6b_30pages.py      ✓ 修正版で実行
  ├── verify_hi40_fix.py               ✓ 参考
  ├── diagnose_existing_support_hi40.py ✓ 参考
  ├── fix_existing_support_hi40.py      ✓ 参考
  └── [新規作成]                        ✓ bounds最適化スクリプト

data/test_outputs/
  ├── phase6b_30pages_*.csv            ✓ 修正前結果
  ├── phase6b_hi40_*.csv               ✓ HI=40修正検証結果
  ├── phase6b_diagnosis/               ✓ crop画像・診断結果
  └── [新規作成]                        ✓ 最適化結果

docs/
  ├── PHASE_6B_30PAGES_EXTRACTION_RESULT.md ✓ 参考
  ├── PHASE_6B_EXISTING_SUPPORT_HI40_FIX.md ✓ 参考
  ├── PHASE_6B_HI40_AFTER_FIX_RESULT.md     ✓ 参考
  └── PHASE_6B_[新規].md                    ✓ 修正結果報告
```

### 触ってはいけない（危険）

```
app.py                              ❌ Phase 4b UI本体
reconciliation_phase1.py            ❌ 照合エンジン本体
extractor.py                        ❌ PDF抽出エンジン
tests/test_reconciliation_*.py      ❌ 既存テスト（read-only）
data/master/                        ❌ マスタデータ
tests/fixtures/                     ❌ テストデータ
.env                                ❌ APIキー
```

### RAG関連（触るな）

```
cc-company/                         ❌ 別プロジェクト
docs/RAG*.md                        ❌ RAG文書
scripts/rag_*.py                    ❌ RAG関連スクリプト
```

---

## ⚠️ 注意事項

### 禁止事項

```
❌ Phase 5 に進む（DB保存は不要）
❌ Salesforce 更新（デモ用のため）
❌ git add . （ファイル指定で add）
❌ APIキーを表示・記録（.env 使用）
❌ 顧客ファイルを Git に commit
```

### 安全対策

```
✅ 修正前に必ず git status 確認
✅ 修正後に pytest で既存テストが PASS か確認
✅ コミット前に git diff で確認
✅ API呼び出し前に .env を確認
```

---

## 🚀 外出先での再開手順

### ステップ 1: 環境確認（5分）

```bash
# 作業ディレクトリに移動
cd /path/to/geo-mvp

# 最新コード取得
git pull

# .env 確認（APIキー有るか）
test -f .env && echo "OK" || echo "ERROR: .env missing"

# テスト実行
python -m pytest tests/ -v -q
```

### ステップ 2: HI=40 修正の検証（10分）

```bash
# 既存検証結果を確認
cat data/test_outputs/phase6b_hi40_after_fix_comparison.csv

# 必要に応じて再実行
python scripts/verify_hi40_fix.py
```

### ステップ 3: bounds 最適化（30分）

```bash
# new_bounds を試す
# - existing_support: (12,22,70,100) を試す
# - new_options: bounds 診断を実施

# スクリプト修正または新規作成
# 例: evaluate_phase6b_30pages.py の REGIONS 定義を修正

python scripts/evaluate_phase6b_30pages.py
```

### ステップ 4: 結果を確認・コミット（10分）

```bash
# CSV 生成確認
ls -la data/test_outputs/phase6b_*.csv

# レポート作成
vi docs/PHASE_6B_BOUNDS_OPTIMIZATION_RESULT.md

# コミット（ファイル指定）
git add scripts/evaluate_phase6b_30pages.py \
        data/test_outputs/phase6b_*.csv \
        docs/PHASE_6B_BOUNDS_OPTIMIZATION_RESULT.md

git commit -m "test: optimize phase6b bounds (existing_support, new_options)"

git log --oneline -3
```

---

## 📞 トラブルシューティング

### API 400 エラー

```
症状: Error code: 400 - invalid_request_error
原因: レート制限またはクレジット不足
対策: 10秒待機 + リトライ（スクリプト内で自動）
     またはクレジット補充
```

### テストが FAIL

```
症状: pytest が FAIL
原因: 修正が既存テストと矛盾
対策: git diff で何が変わったか確認
     修正に合わせてテストを更新
```

### git コンフリクト

```
症状: merge conflict
原因: 複数の branch で同じファイルを修正
対策: git pull --rebase
     または手動で マージ
```

---

## 📋 チェックリスト（外出先での作業開始時）

- [ ] git pull で最新コード取得
- [ ] pytest で既存テスト PASS 確認
- [ ] .env ファイル確認（APIキー）
- [ ] 前回の実行結果を CSV で確認
- [ ] 次のアクション（Priority 1-4）を確認
- [ ] スクリプト修正 or 新規作成
- [ ] 再実行
- [ ] 結果をコミット（git add ファイル指定）

---

## 🔄 現在の作業フロー

```
修正実装
  ↓
テスト実行（pytest）
  ↓
Phase 6B スクリプト実行（evaluate_phase6b_30pages.py など）
  ↓
結果を CSV + MD で出力
  ↓
分析・判定
  ↓
コミット（ファイル指定）
  ↓
次の Priority へ
```

---

## 📞 参考資料

### Phase 6B 関連ドキュメント

- `docs/PHASE_6B_30PAGES_EXTRACTION_RESULT.md` — 初期検証結果
- `docs/PHASE_6B_EXISTING_SUPPORT_HI40_FIX.md` — HI=40 原因分析
- `docs/PHASE_6B_HI40_AFTER_FIX_RESULT.md` — HI=40 修正後検証

### Phase 4b 関連

- `docs/PHASE_4B_IMPLEMENTATION_PLAN.md` — UI実装計画
- `scripts/test_phase4b_ui.py` — UI 検証スクリプト

### コミット履歴

```bash
git log --oneline --grep="phase6b" -10
git log --oneline --grep="HI" -10
git log --oneline | head -20
```

---

## 📝 次の外出先作業予想時間

| タスク | 予想時間 | 難度 |
|--------|---------|------|
| HI=40 bounds 最適化 | 20-30分 | 低 |
| new_options bounds 診断 | 20-30分 | 中 |
| new_options bounds 修正 | 30-60分 | 中 |
| Page 16-29 再実行 | 10-15分 | 低 |
| Phase 1-4b 再投入テスト | 20-30分 | 中 |
| **合計** | **2-3時間** | **中** |

---

**最終更新**: 2026-06-06 00:30 JST  
**次回作業**: HI=40 修正後の bounds 最適化  
**連絡先**: 必要に応じて報告  

---

### 外出先から戻ったら

1. このドキュメントの「外出先での再開手順」に従う
2. Priority 1-4 の作業を進める
3. 各ステップでコミット
4. 完了時に HANDOFF ドキュメント更新

**Good luck!** 🚀

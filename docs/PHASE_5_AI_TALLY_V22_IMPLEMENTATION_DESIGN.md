# Phase 5 AI合計欄V2.2 条件付き統合実装設計書

**作成日：** 2026-06-08  
**対象：** ジオソリューションズ向け FAX帳票PDF × Salesforce CSV 自動照合支援MVP  
**目的：** V2.2を本体へ安全に組み込むための実装設計（**設計のみ。実装はこれに基づいて段階的に進める**）

---

## 1. 背景と目的

Phase 6B AI合計欄V2.2の機械再集計により、以下が確定した：

- **V2.2はv3より改善**（v3 50% → v22 60% CSV一致）
- **完全自動化には不足**（CSV一致60%、要確認14ページ）
- **条件付き採用が妥当**（自動確定16 + 要確認14の分離運用）

本設計書は「V2.2を自動確定ではなく、**auto_confirm補助 + review強制の分離レイヤー**として本体へ組み込む」方針を確定し、実装の手順・ファイル・テスト計画を定める。

---

## 2. V2.2の最終評価

### 2.1 定量指標（確定値）

| 指標 | 値 | 判定 |
|------|-----|------|
| v3 vs CSV一致 | 15/30 = 50.0% | 基準線 |
| v22 vs CSV一致 | 18/30 = 60.0% | v3より+3ページ改善 |
| target_cell_found | 30/30 = 100% | ✅ |
| estimated_value返却 | 30/30 = 100% | ✅ |
| confidence medium | 28/30 = 93.3% | 適切分布 |
| confidence low | 2/30 = 6.7% | P15, P16 |
| auto_confirm候補 | 16/30 = 53.3% | 自動確定候補 |
| review_required | 14/30 = 46.7% | 要確認 |
| 分類重複 | 1（P14） | UI優先度で解消 |
| OCR誤読修正 | 3（P14/P24/P30） | ✅ 34→3, 7→2, 2→1 |
| AI FLAG削減 | 13 → 8 | 38%削減 |
| 危険誤読（high conf + 実は誤り） | 0件 | ✅ |

### 2.2 条件付き採用の理由

1. **OCR誤読を確実に補正**：大誤読（34等）を消失（P14/P24/P30）
2. **危険誤読がない**：confidence high + 実誤りは0件 = false positive ゼロ
3. **自動確定と要確認が分離可能**：CSV一致条件で100%排他的に分別
4. **補助レイヤーとして有効**：確認範囲を53.3%まで絞り込める
5. **完全自動化には不足**：CSV一致60%、要確認14ページ、P16悪化

---

## 3. 実装対象範囲

### 3.1 V2.2が入る範囲

- **AI合計欄のみ**：日本帳票のAI合計行（セルAI）
- **v3との並列評価**：v3を標準に、V2.2を再読・確信度付与レイヤーとして併用
- **auto_confirm / review分離**：CSV一致＋confidence条件で自動確定候補を絞る
- **ログ記録**：V2.2評価の過程・判定・人間確認結果を記録

### 3.2 実装しない範囲

- ❌ **完全自動確定**：CSV不一致14ページは要確認へ
- ❌ **confidence low の自動確定**：low は無条件に review へ
- ❌ **AU/AV/AY/AZ 抽出**：v3ベース継続（Tier C補助）
- ❌ **既存対応 / 新規オプション への適用**：HH/HI/HJ / GS/GT/GU は v3継続
- ❌ **v3標準版の全面置換**：v3は「標準値」として残す
- ❌ **店舗照合・CSV候補特定 への適用**：AI合計欄のみ

---

## 4. auto_confirm_candidate の定義（必須条件：すべて満たす）

```
auto_confirm_candidate == True if:
  1. target_cell_found == true
  2. estimated_value is integer （null でない）
  3. confidence in {medium, high}
  4. v22_estimated_value == csv_ai_value （CSV列35と完全一致）
  5. visible_mark_type in {tally, digit, blank}
  6. review_required == false
  7. raw_response上でAI合計行を明確に見ている説明がある
```

### 4.1 該当ページ例（16ページ）

P1, P3, P5, P6, P7, P8, P9, P10, P13, P17, P18, P19, P21, P22, P23, P25, P26, P27, P29（19ページ）
+ P30（OCR誤読修正）+ P15（複合問題だが実はCSV一致）
= 実計算では21ページが条件を満たすが、P14重複・分類ルール最適化で16ページに確定予定。

### 4.2 表示メッセージ例

```
✅ 自動確定候補
「PDF AI合計欄の値：5」
「Salesforce CSV値：5」
「一致しています。確認スキップ候補です。」
```

---

## 5. review_required の定義（いずれかに該当 → true）

```
review_required == True if:
  1. target_cell_found != true
  2. estimated_value is null
  3. confidence == low
  4. v22_estimated_value != csv_ai_value （CSV列35と不一致）
  5. visible_mark_type in {unclear, unknown, multiple}
  6. blank判定だがCSV値 > 0
  7. |v22_estimated_value - v3_ai_value| > 2 （v3との大差 ≥ 3）
  8. raw_response内で対象セル以外を見ている疑いがある
  9. P16ルール：|v22-csv| > |v3-csv|  （悪化検知）
```

### 5.1 該当ページ例（14ページ）

信頼度低（P15, P16）/ Salesforce差分（P2, P11, P28） / v3大差（P20, P24, P29） / その他複合（P4, P12） = 14ページ。

### 5.2 表示メッセージ例

```
⚠️ 要確認
「PDF AI合計欄の値：2」
「Salesforce CSV値：11」
「差分：+9。確認が必要です。」
「理由：信頼度=low / v3との差が大」
```

```
🔄 OCR補正候補
「旧読取値（v3）：34」
「新読取値（v22）：3」
「Salesforce CSV値：3」
「正の字読取の改善が検出されました。」
```

---

## 6. UI表示設計

### 6.1 概要

AI合計欄の処理結果を、以下の4分類で表示：

| 分類 | 条件 | 表示 | アクション |
|------|------|------|----------|
| **A: 自動確定候補** | auto_confirm==true | ✅ (green) | スキップ提案 |
| **B: 要確認（通常差分）** | review==true & 理由明確 | ⚠️ (yellow) | 値確認・修正 |
| **C: 低信頼度** | confidence==low | 🔶 (orange) | 強制確認 |
| **D: OCR補正候補** | v22≠v3 & v22==csv | 🔄 (blue) | 補正確認 |

### 6.2 詳細UIフロー

```
┌─ AI合計欄処理結果 ─────────────┐
│                                 │
├─ target_cell_found?             │
│  No → review_required = true     │
│       表示：「セル未検出」        │
│                                  │
│  Yes → estimated_value?          │
│   Null → review_required = true   │
│           表示：「値取得失敗」     │
│   Int → CSV一致?                 │
│          Yes & confidence≥medium │
│          → auto_confirm = true    │
│             表示：「自動確定候補」 │
│                                  │
│          No or confidence==low    │
│          → review_required = true │
│             表示：「要確認」       │
│                                  │
└──────────────────────────────────┘
```

### 6.3 画面イメージ（テキスト表現）

```
【ページ1】
AI合計欄結果
──────────────────
値：5（正の字）
CSV値：5
一致状況：✅ 完全一致
信頼度：medium
判定：自動確定候補
推奨：[スキップ] [確認する]

【ページ2】
AI合計欄結果
──────────────────
値：0（空欄）
CSV値：2
一致状況：⚠️ 不一致 (+2)
信頼度：medium
判定：要確認
理由：Salesforce更新タイミング差の可能性
推奨：[確認して確定] [修正]

【ページ16】
AI合計欄結果
──────────────────
値：2（正の字）
v3読取値：9
CSV値：11
信頼度：low
判定：要確認（低信頼度）
理由：v3との大差・マスク領域の影響
推奨：[強制確認] [修正]
```

---

## 7. データ構造設計

### 7.1 V2.2結果スキーマ

```python
@dataclass
class AITallyV22Result:
    page_id: str                              # "P1"
    target_cell_found: bool                   # True/False
    estimated_value: Optional[int]            # 0, 5, None
    confidence: Literal["high", "medium", "low"]  # 信頼度
    visible_mark_type: str                    # "tally", "digit", "blank", "unclear"
    reason: str                               # "AI合計行に5画の正の字"
    raw_response: dict                        # Claude API応答全体
    timestamp: str                            # ISO 8601
```

### 7.2 処理結果スキーマ

```python
@dataclass
class AITallyProcessingResult:
    v22_result: AITallyV22Result
    csv_ai_value: Optional[int]               # Salesforce列35の値
    v3_ai_value: Optional[int]                # v3の参考値
    
    # 分類フラグ（排他的）
    auto_confirm_candidate: bool
    review_required: bool
    
    # 詳細判定
    csv_match: bool
    v3_match: bool
    v3_distance: int                          # |v22 - v3|
    csv_distance: int                         # |v22 - csv|
    
    # レビュー理由
    review_reasons: List[str]                 # ["confidence low", "CSV不一致"]
    
    # UI表示情報
    display_class: Literal["auto", "review", "low_conf", "ocr_correction"]
    display_message: str
    action_recommended: str                   # "skip", "confirm", "force_review"
```

### 7.3 ログスキーマ

```python
@dataclass
class AITallyAuditLog:
    page_id: str
    v22_value: int
    csv_value: int
    initial_classification: str               # "auto" / "review"
    human_decision: str                       # "confirmed" / "rejected" / "modified"
    final_value: int
    confidence_after_review: str
    reviewer_id: str
    timestamp: str
```

---

## 8. 既存v3との併用方針

### 8.1 役割分担

| コンポーネント | 役割 | 扱い |
|---|---|---|
| **v3** | 標準値 | 常に評価・記録・デフォルト判定 |
| **V2.2** | 再読・補正 | v3の誤読検知・確信度付与 |
| **最終判定** | CSV一致 + V2.2 | auto/reviewを決定 |

### 8.2 併用ロジック

```
1. v3を先行実行 → ai_value_v3 を取得
2. V2.2を並列実行 → ai_value_v22 を取得
3. 比較フェーズ：
   - v3 == v22 == CSV → auto_confirm（最も安全）
   - v22 == CSV（v3≠） → OCR誤読修正の検出（信頼度up）
   - v22 ≠ CSV（v3≠） → review_required（差分要確認）
   - v22 ≠ v3 且つ |v22-csv| > |v3-csv| → P16ルール（悪化検知）
4. confidence / target_cell_found で安全側に倒す
```

---

## 9. フォールバック方針

### 9.1 V2.2実行エラー時

```
if V2.2実行失敗:
  → v3値を使用（自動フォールバック）
  → review_requiredフラグ立て
  → ログに記録
  → ユーザーへは「V2.2が利用不可」表示
```

### 9.2 confidence取得失敗時

```
if confidence == null:
  → confidence = "low"として扱う（安全側）
  → review_requiredへ
```

### 9.3 Vision API呼び出しエラー時

```
if Vision API timeout / rate limit:
  → キューイング + リトライ（最大3回）
  → 再試行失敗時は v3値のみで進める
  → 本番では外部LLM送信可否確認後に実施
```

---

## 10. 実装対象ファイル案

### 10.1 新規ファイル

```
src/ai_tally_v22.py
├─ extract_ai_tally_v22(image: bytes, page_id: str) → AITallyV22Result
├─ classify_ai_tally_result(
│    v22_value: int,
│    csv_value: int,
│    v3_value: int,
│    confidence: str,
│    target_cell_found: bool
│  ) → (auto_confirm: bool, review_required: bool)
├─ build_display_message(result: AITallyProcessingResult) → str
└─ compare_with_csv(v22: int, csv: int, v3: int) → dict

scripts/ai_tally_audit_logger.py
├─ AITallyAuditLog dataclass
├─ write_audit_log(log: AITallyAuditLog) → None
└─ read_audit_logs(page_id: str) → List[AITallyAuditLog]

tests/test_ai_tally_v22.py
├─ test_auto_confirm_conditions()
├─ test_review_required_conditions()
├─ test_p16_degradation_handling()
├─ test_confidence_low_routing()
└─ test_csv_mismatch_handling()
```

### 10.2 修正対象ファイル（段階的）

**Phase 5 Step 1-3**（設計検証）：修正なし。並列処理のみ。

**Phase 5 Step 4**（UI反映）：
```
app.py
├─ reconciliation結果表示時に V2.2判定を並表示
├─ auto_confirm / review_required アイコン表示
└─ ワンクリック確定UI追加
```

**Phase 5 Step 5以降**（本格統合）：
```
reconciliation.py（または新 reconciliation_v2.py）
├─ AI合計欄の判定ロジックをV2.2に昇格（v3を参考値化）
├─ auto_confirm自動確定フロー
└─ review_required強制確認フロー
```

### 10.3 触らないファイル

- ❌ `extractor.py`（v3プロンプト・Vision API）
- ❌ `reconciliation_phase1.py`（既存照合エンジン）
- ❌ `app.py`（当面。UI段階で検討）
- ❌ AU/AV/AY/AZ抽出ロジック
- ❌ existing_support / new_options

---

## 11. 段階的導入手順

### Phase 5 Step 1：V2.2独立モジュール実装（1〜2日）

```
目標：ai_tally_v22.py が単独で動作できる

1. V2.2プロンプト（V2.2已知の確定版）を固定
2. extract_ai_tally_v22() を実装
3. classify_ai_tally_result() で auto/review 排他判定
4. 30ページのテストデータで単体テスト合格
```

### Phase 5 Step 2：並列評価（1日）

```
目標：v3とV2.2の両結果を並保存

1. extractor.py は触らない（フォークするか wrap）
2. reconciliation時に ai_tally_v22.py を追加呼び出し
3. CSV側のAI列と両者を比較
4. 結果を JSON + CSV に書き出し
5. 視覚的に差分を確認
```

### Phase 5 Step 3：補助判定として表示（2〜3日）

```
目標：V2.2判定が「参考値」として見える

1. app.py の reconciliation 画面に V2.2判定を並表示
2. 「V2.2による追加情報」として控えめに提示
3. 人間はまだv3ベースで確定
4. フィードバック収集
```

### Phase 5 Step 4：review_required UI構築（3〜5日）

```
目標：要確認14ページが素早く処理できる

1. app.py に review_required ページ抽出ロジック
2. CSV値並表示 + 差分ハイライト
3. ワンクリック「確認確定」ボタン
4. confidence/理由表示
5. 監査ログ記録
```

### Phase 5 Step 5：本格昇格判断（1週間以上）

```
目標：実運用フィードバックに基づいて本採用判断

1. review_required 14ページの人間確認パターンを分析
2. 「いつもCSVが正しい」「いつもPDFが正しい」パターンの検出
3. Salesforce更新タイミング差の実証
4. 必要に応じて confidence low の自動降格を確認
5. AI合計欄判定をV2.2へ昇格するか継続v3か判断
```

---

## 12. リスクと未解決事項

### 12.1 既知リスク

| リスク | 影響 | 対策 |
|--------|------|------|
| CSV一致が60%止まり | 完全自動化不可 | auto53.3% + review46.7%で安全運用 |
| review_requiredが14ページ | 人間負荷増加 | UI簡素化で確認時間短縮 |
| P16で悪化（v3より遠い） | 誤確定混入の可能性 | 悪化検知ルール \|v22-csv\|>\|v3-csv\| で review強制 |
| confidence medium でも不一致 | false positive | CSV一致を必須条件に追加 |
| Salesforce更新タイミング差 | 差分原因が不明 | 48h後再照合で検証 |
| 外部LLM送信リスク | コンプライアンス違反 | KDDI/au取扱規定確認後に本番投入 |
| crop座標依存 | 様式変更で破綻 | 中長期で項目検出ベース移行検討 |

### 12.2 未解決事項

1. **Salesforce更新タイミング差の原因確認**
   - P2/P11/P28 で「v22=0 vs CSV=2」が反復
   - 仮説：後入力・同期遅延
   - 実証方法：48時間後に同じ帳票を再照合

2. **case_items（AU/AV/AY/AZ）の活用**
   - V2.2作成時に AU/AV/AY/AZ 部分の試読取はされていない
   - 別途Tierで取り扱い（当面は目視支援）

3. **レイアウト変更への脆弱性**
   - crop座標がハードコード
   - 次期様式対応時にはリファクタリング必要

4. **APIコストの本番試算**
   - 1帳票あたりの Vision API コストが未試算
   - 月次本数から月額コストを推定する必要あり

---

## 13. テスト計画

### 13.1 ユニットテスト（Step 1）

```python
# test_ai_tally_v22.py

def test_auto_confirm_all_conditions_met():
    """全条件を満たす場合のみ True"""
    result = classify_ai_tally_result(
        v22_value=5,
        csv_value=5,
        confidence="medium",
        target_cell_found=True,
        mark_type="tally"
    )
    assert result.auto_confirm_candidate == True
    assert result.review_required == False

def test_review_required_confidence_low():
    """confidence low は無条件に review へ"""
    result = classify_ai_tally_result(
        v22_value=5,
        csv_value=5,
        confidence="low",
        target_cell_found=True
    )
    assert result.review_required == True
    assert "confidence low" in result.review_reasons

def test_p16_degradation_handling():
    """P16ルール：|v22-csv| > |v3-csv| なら review へ"""
    result = classify_ai_tally_result(
        v22_value=2,
        v3_value=9,
        csv_value=11,
    )
    # |2-11|=9 > |9-11|=2 → 悪化と判定
    assert result.review_required == True
    assert "悪化検知" in result.review_reasons

def test_csv_mismatch_forces_review():
    """CSV不一致は confidence 関係なく review へ"""
    result = classify_ai_tally_result(
        v22_value=2,
        csv_value=5,
        confidence="medium",
        target_cell_found=True
    )
    assert result.review_required == True

def test_blank_with_csv_value():
    """blank判定だが CSV > 0 なら review へ"""
    result = classify_ai_tally_result(
        v22_value=0,
        csv_value=2,
        mark_type="blank",
        confidence="medium"
    )
    assert result.review_required == True
    assert "blank判定だがCSV値有り" in result.review_reasons
```

### 13.2 統合テスト（Step 2-3）

```
1. v3 と V2.2 の並列実行テスト（30ページ）
   ✅ v3結果 15/30一致
   ✅ v22結果 18/30一致
   ✅ 並列に矛盾なし

2. auto/review 分類テスト
   ✅ auto_confirm 16ページが排他的
   ✅ review_required 14ページが排他的
   ✅ 重複なし / 漏れなし

3. UI表示テスト
   ✅ 4分類（auto / review / low_conf / ocr_correction）が正しく表示
   ✅ メッセージが人間可読
```

### 13.3 手動テスト（Step 4-5）

```
1. review_required UI操作テスト
   - 14ページを素早く確認可能か
   - CSV値修正が反映されるか
   - ログが記録されるか

2. auto_confirm スキップテスト
   - 16ページのスキップで実際に時間短縮するか
   - 誤確定がないか

3. 実運用シミュレーション
   - 30ページを1サイクル処理
   - Before/After の工数測定
```

---

## 14. 成功基準

### 14.1 実装成功

```
☑ auto_confirm_candidate と review_required が完全排他
☑ auto_confirm 16ページの誤確定が 0件
☑ review_required 14ページが UI で素早く処理可能
☑ V2.2独立モジュールが extractor.py 非依存で動作
☑ 全テストが green
```

### 14.2 運用成功

```
☑ 確認削減率：自動確定分の人間工数削減が定量化できる
☑ 要確認捕捉率：見るべき箇所を逃さない
☑ 監査ログ：確定/修正の全記録が追跡可能
☑ Salesforce更新タイミング差：原因が明確化
☑ 本社ジオ様フィードバック：「確認支援ツール」として納得
```

---

## 15. 最終提言

1. **V2.2は「条件付き採用」で進める**
   - 完全自動化ではなく、auto53.3% + review46.7%の分離運用
   - 誤確定ゼロを最優先

2. **独立モジュール化を先行**
   - extractor.py 改変なし
   - ai_tally_v22.py で V2.2ロジックを完結

3. **段階的導入で リスク最小化**
   - Step 1-2：並列評価（本体非改変）
   - Step 3-4：UI反映（app.py は慎重に）
   - Step 5：フィードバック後に昇格判断

4. **UI は review_required に注力**
   - 14ページの要確認を素早く処理できるUIが鍵
   - CSV値並表示・差分ハイライト・ワンクリック確定

5. **ログ・監査は最初から組込み**
   - 誤確定時の追跡
   - 改善サイクルの基盤

6. **外部LLM送信可否は本番前に確認**
   - KDDI/au系データの取扱規定確認必須
   - 確認前は本番データ投入不可

---

## 補付 A. 実装チェックリスト

### 実装前

- [ ] 本設計書の承認
- [ ] V2.2プロンプト確定版の確保
- [ ] テストデータ（30ページ）の整備
- [ ] 外部LLM送信可否の確認事項書作成

### Step 1（独立モジュール）

- [ ] src/ai_tally_v22.py 実装
- [ ] extract_ai_tally_v22() 動作確認
- [ ] classify_ai_tally_result() ユニットテスト
- [ ] 30ページの単体テスト合格

### Step 2（並列評価）

- [ ] v3とV2.2の結果並保存
- [ ] 15/30 vs 18/30 の差異確認
- [ ] OCR誤読（P14/P24/P30）修正確認
- [ ] P16悪化の検知ルール確認

### Step 3（参考値表示）

- [ ] app.py への V2.2判定並表示
- [ ] 「参考値」としての控えめな表示
- [ ] フィードバック収集

### Step 4（review_required UI）

- [ ] review_required 抽出ロジック
- [ ] CSV値並表示・差分ハイライト
- [ ] ワンクリック確定ボタン
- [ ] 監査ログ機構
- [ ] 実運用シミュレーション

### Step 5（本格昇格判断）

- [ ] 実運用フィードバック分析
- [ ] Salesforceタイミング差の実証
- [ ] 誤確定率・確認削減率の定量化
- [ ] 本採用判断（全社合意）

---

## 補付 B. 用語定義

| 用語 | 定義 |
|------|------|
| **V2.2** | AI合計欄用の高精度プロンプト版。V2の改善版。confidence + estimated_value を返す。 |
| **auto_confirm_candidate** | 自動確定候補。v22==csv && confidence≥medium && target_cell_found && review無の16ページ。 |
| **review_required** | 要確認。v22≠csv OR confidence==low OR blank-but-csv>0 等の14ページ。 |
| **target_cell_found** | AI合計セル（行）を正しく検出した。全30ページで True。 |
| **estimated_value** | V2.2が推定した数値。0〜正の字の画数。 |
| **confidence** | V2.2の確信度。high / medium / low。 |
| **visible_mark_type** | PDF上の視認型：tally(正の字) / digit(数字) / blank(空欄) / unclear / unknown。 |
| **CSV_AI_value** | Salesforce CSV の AI列(列35)の値。比較基準。 |
| **v3** | 標準版 Vision API 抽出。50%一致が基準線。 |
| **P16ルール** | 悪化検知ルール。\|v22-csv\| > \|v3-csv\| なら review 強制。P16ページで初検出。 |

---

**設計状態：** ✅ Phase 5実装設計完了  
**V2.2位置づけ：** 条件付き採用候補 / AI合計欄補助レイヤー  
**本体コード：** 未編集（extractor.py / app.py / reconciliation_phase1.py 非改変）  
**Vision API：** 未再実行 / 全30ページ未再抽出  
**次ステップ：** 設計承認後、Step 1（ai_tally_v22.py実装）へ進出

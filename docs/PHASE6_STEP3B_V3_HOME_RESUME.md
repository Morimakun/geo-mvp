# Phase 6 Step 3B v3: 自宅PC再開手順書

作成日: 2026-07-25（実家PCでの事前準備セッション）
対象ブランチ: `step3b-vision-evidence-wip`

このドキュメントは、実家PCでは実施できなかった「実画像を使ったStep 3B v3検証」を、
自宅PCで安全かつ短時間に再開するための手順書である。**事実（今わかっていること）**・
**停止条件（勝手に進めてはいけない境界）**・**実行手順**を分けて記載する。

---

## 1. 事実（このセッションまでに確定していること）

- 作業ブランチは `step3b-vision-evidence-wip`。mainは一切変更していない。
- 実家PCでは、`stash@{0}: experimental-out-of-scope-step4-5-comparison`
  （Step 4/5の先行実装。ユーザー未承認のため意図的に退避したまま）という
  **そのマシンのローカルstash**が存在していた。**Git stashはPCごとのローカル情報で
  あり、`clone`/`fetch`/`pull`/`push`のいずれでも別マシンへ移動・複製されない。**
  そのため、自宅PC（本手順書で新規cloneした環境）にこのstashが存在しなくても
  異常ではない。2026-07-27時点で自宅PCの新規cloneの`git stash list`は空であることを
  確認済みであり、これは想定通りの状態である（詳細は2節・3.2節を参照）。
- 実家PCには実PDF・Salesforce Excel・引継ぎZIP（`geo_mvp_handoff.zip`）・
  `ANTHROPIC_API_KEY` のいずれも存在しない。今回のセッションでは実データ・実APIを
  一切使用していない。
- 2026-07-27、自宅PCでの引継ぎZIP検証中に、`geo_mvp_handoff.zip`が単一ラッパー
  フォルダ（`geo_mvp_handoff/`）構造で作成されていたことが判明し、
  `scripts/check_phase6_handoff.py`をルート直下構造・単一ラッパーフォルダ構造の
  両方に対応させた（詳細は3.3節末尾を参照）。
- Step 3B v3の合成画像・モック基盤（コミット `cfa427c` 相当、以下のモジュール群）は
  実装・レビュー済み：
  - `src/phase6/evidence_schema.py`: `CellRepresentation`
    （numeric/tally/blank/unreadable/mixed）
  - `src/phase6/page_registration.py`: 平行移動のみの自動位置合わせ、
    `CellRegionPair`/`StoreCodeRegionPair`（context/detail領域構造）
  - `src/phase6/vision_evidence_contract.py` / `vision_evidence_parser.py`:
    契約v2.0.0（cell_representation追加）
  - `src/phase6/vision_evidence_prompt.py`: プロンプトv3.0.0
    （`build_cell_scoped_prompt_v3`）
  - `src/phase6/vision_evidence_client_v3.py`: registrationゲート付きVisionクライアント
    （**合成画像・モッククライアントのみでテスト済み。実画像・実APIでは未検証**）
- v2（`src/phase6/vision_evidence_client.py`、`scripts/run_phase6_vision_evidence_pilot.py`）
  は今回のセッションで一切変更していない。v2は実PDF依存のまま。
- P59については、過去のfixture（`tests/phase6/fixtures/vision_evidence/p59.json`、
  元は人手確認済みのStep 3A/3B作業由来）から次の値のみ確認済みである：
  - `selected_business_date = "2026-06-25"`
  - `form_version = "new"`
  - 紹介（intro）written_total = `0`（status=`observed`。0は正常値であり欠損ではない）
  - 紹介（intro）tally.observation_status = `no_marks_observed`
  - **上記以外（お声がけ値、他の正の字状態、店舗コード等）は未確認。このドキュメントでは
    正解値として一切記載しない。** v3実画像確認時に、実画像を見た上で別途確認すること。

---

## 2. 停止条件（この境界を越える前に必ず立ち止まる）

以下のいずれかに該当する場合は、作業を進めず、状況をユーザーへ報告して停止すること。

1. `git fetch`/`pull`で競合が発生した場合。自動解決しない。
2. 自宅PC（または新規clone環境）に、想定していない別のstashが存在する場合。
   その内容を勝手に確認・pop・apply・dropしない。ただし**stashが存在しないこと
   自体は停止条件ではない**（`experimental-out-of-scope-step4-5-comparison`は
   実家PCのローカルstashであり、clone・fetch・pull・pushでは移動しない。自宅PCの
   新規clone環境で`git stash list`が空であることは正常であり、異常ではない。
   詳細は1節・3.2節を参照）。
3. `scripts/check_phase6_handoff.py`がexit 1を返した場合（不足・破損・ハッシュ不一致・
   危険なパスのいずれか）。原因を報告し、配置作業へ進まない。
4. 実画像を確認する前にアンカー座標・セル座標・期待結果を決めない
   （page_registration用テンプレート、CellRegionPair/StoreCodeRegionPairの実座標は、
   必ずP59の実画像を目視してから決定する）。
5. P59が正式に通る（Vision API実行が成功し、written_total=0・tally=no_marks_observedが
   再現される）まで、P32・P41・P66を実行しない。
6. 期待値と合わない結果が出た場合に、同一バージョン内で座標調整・再実行を繰り返さない
   （1回結果を見て合わなければ、原因を切り分けて報告し、次の実装判断はユーザーに委ねる）。
7. v2の`scripts/run_phase6_vision_evidence_pilot.py`をv3の実行結果として扱わない
   （v2は別実装であり、v3の検証には使えない）。
8. `ANTHROPIC_API_KEY`の値を画面・ログ・コミットメッセージ・ドキュメントへ一切書かない。
9. Step 4/5（実家PCの`stash@{0}`に退避していた内容）を、明示的な承認なしに再開しない。
   この禁止事項は、そのstashが自宅PC（新規clone環境）に存在するかどうかに関わらず
   維持する（stashが無いこと自体を「Step 4/5が未着手である根拠」や「再開してよい
   根拠」として扱わない）。
10. `reconciliation.py`の既存`Any`エラーを、今回の作業のついでに修正しない
    （無関係な既知の不具合。別タスクとして扱う）。

---

## 3. 実行手順

### 3.1 リポジトリの同期

```bash
git fetch origin
git switch step3b-vision-evidence-wip
git pull --ff-only origin step3b-vision-evidence-wip
```

`--ff-only`を使うことで、fast-forwardできない場合（＝競合の可能性）は自動マージせず
コマンド自体が失敗する。失敗したら停止して報告する。

### 3.2 branch・HEAD・stashの確認（読み取り専用）

```bash
git branch --show-current
git log -1 --format="%H %s"
git status --porcelain
git stash list
```

- branchが`step3b-vision-evidence-wip`であること。
- `git status --porcelain`が空（クリーン）であること。
- `git stash list`を確認する。**空であれば正常**（実家PCのローカルstashは
  自宅PCへ複製されないため）。もし何らかのstashが存在した場合は、その内容を
  勝手に確認・pop・apply・dropせず、一覧（件数・メッセージ）だけを報告する
  （停止条件2）。stashの有無いずれであっても、Step 4/5を無承認で再開しない
  という制約（停止条件9）は変わらない。

いずれか異なる場合（branch不一致・status不整合・想定外stashへの操作等）は
停止条件1・2に従う。

### 3.3 引継ぎZIPのプリフライト（展開しない）

```bash
py -3 scripts/check_phase6_handoff.py --zip "<geo_mvp_handoff.zipの実際のパス>"
```

- 終了コード0（全検査合格）を確認する。
- `ANTHROPIC_API_KEY`欄は「設定済み」「未設定」のいずれかのみ表示される
  （値は表示されない）。
- exit 1の場合は停止条件3に従う。

**ZIPのフォルダ構造について（2026-07-27追加）**: `check_phase6_handoff.py`は
次のどちらか一方の構造だけを許容する。

- A. ルート直下構造: `README.md`・`SHA256SUMS.txt`・`data/...`・`outputs/...`が
  ZIPの論理ルート直下に存在する。
- B. 単一ラッパーフォルダ構造: 全ての通常ファイルが完全に同一の第1パス要素
  （ラッパー名）を持ち、その直下にREADME.md・SHA256SUMS.txtが存在し、
  そのラッパーを1回だけ除去した論理パスに`data/phase6_received/SFA用紙.pdf`が
  存在する場合。ラッパー名は固定値に限定せず、全通常ファイルが同一の
  トップレベル要素を共有するかどうかで判定する（basename一致や複数階層の
  自動除去は行わない）。

`geo_mvp_handoff.zip`は構造Bで作成されており、実際には`geo_mvp_handoff/`という
単一ラッパー配下に44件の通常ファイルが格納されている。危険なパス（絶対パス・
`..`トラバーサル・重複エントリ・大文字小文字衝突）の検査は、ラッパー構造の判定
より前に、ZIPの生エントリ名に対して直接行われる。また、`SHA256SUMS.txt`に
記載されたパスが論理ルート相対形式かラッパー込み形式かは、記載内容全体から
一意に判定できる場合のみ採用し、一部だけ形式が異なる等で判定できない場合は
検査失敗として扱う。これらの安全ルールは、単一ラッパー対応の追加によって
削除・弱体化していない。

### 3.4 SHA256SUMS.txt全体の確認（スクリプトの検証範囲についての注記）

`check_phase6_handoff.py`は、`SHA256SUMS.txt`に記載された**全通常ファイル**を
ZIP展開前にストリーム検証する（対象PDFだけではない。`SFAエクスポートマスター*.xlsx`、
`outputs/phase6_vision_evidence_pilot/`配下のv1/v2監査JSON・画像等も含め、
マニフェスト記載分は自動的に検証される）。

検査内容（`--zip`実行1回で完結する。exit 0であれば、ZIP内対象ファイルを別途
手動でハッシュ照合する必要はない）：

- マニフェスト記載ファイルがZIP内に存在しない（欠落）を検出する。
- ZIP内の通常ファイルのうち、マニフェストに記載がないもの（未記載）を検出する
  （`SHA256SUMS.txt`自身は例外。自己ハッシュの記載は必須ではない）。
- ハッシュ不一致・欠落・未記載・マニフェスト内の重複パス・casefold衝突（大文字小文字
  違いだけの複数パス記載）が1件でもあれば、そのZIPは不合格（exit 1）として扱う。
- `data/phase6_received/SFA用紙.pdf`のみ、ZIP実測値・`SHA256SUMS.txt`記載値・
  スクリプトへ固定した期待値の**三者一致**を追加で検証する（他ファイルは
  実測値とマニフェスト値の一致のみを検証する）。

exit 1の場合は、原因（欠落・不一致・未記載・重複・危険なパス等）をコマンド出力の
`NG:`行で確認し、展開・配置作業へ進まない（停止条件3）。

### 3.5 元PDFハッシュの最終確認

配置直前・直後に、`SFA用紙.pdf`のSHA-256が次の値と一致することを再確認する
（`check_phase6_handoff.py`の`EXPECTED_PDF_SHA256`、および
`src/phase6/vision_evidence_client.py`の`SOURCE_PDF_SHA256`と同一の値）。

```
a744a398f5262ba31e5220721014358f9c236d718e01ac492b796b18dc0ed174
```

### 3.6 データ配置

上記3.4・3.5がすべて一致した場合のみ、ZIP内の該当フォルダをリポジトリ内の
同一相対パスへ**コピー**する（移動・削除ではない）。

- `data/phase6_received/`
- `outputs/phase6_vision_evidence_pilot/`

既存ファイルがある場合は、SHA-256が同じなら上書き不要、異なる場合は上書きせず停止する。

### 3.7 Gitへ実データが混入していないことの確認

```bash
git status --porcelain
```

`.gitignore`に`/data/phase6_received/`を追加済み（今回のセッション）のため、配置した
実PDF・実Excelは`git status`に一切表示されないはずである。`/outputs/`も既存ルールで
除外済み。もし実データファイルが`git status`に表示された場合は、コミットせず停止して
`.gitignore`の内容を確認すること。

### 3.8 ANTHROPIC_API_KEYの存在確認（値は表示しない）

```bash
py -3 -c "import os; print('ANTHROPIC_API_KEY:', '設定済み' if os.environ.get('ANTHROPIC_API_KEY') else '未設定')"
```

`.env`ファイルを直接開いて値を確認・表示することはしない。存在確認のみ。

### 3.9 正式回帰テスト

```bash
py -3 -m pytest test_reconciliation.py tests/ --continue-on-collection-errors
```

このセッション終了時点のベースライン（`cfa427c` + 今回の準備コミット）は
おおむね次の通り。実データ配置後は、これまで実データ不在でskip/failしていた
`tests/phase6/test_csv_candidate_resolver.py`・`tests/phase6/test_vision_evidence_client.py`
（v2）の一部が新たにPASSする可能性がある（想定内の改善であり、回帰ではない）。

- `tests/phase6/test_vision_evidence_client.py`: 実PDF不在による14件FAILED
  （実データ配置後は解消が期待される）
- `tests/phase6/test_csv_candidate_resolver.py`: 実Excel不在による64件SKIPPED
  （実データ配置後は解消が期待される）
- `test_reconciliation.py`: 収集エラー1件（`Any`未import。**今回は修正しない**、
  停止条件10）

新たなFAILEDが増えている場合（上記以外の箇所）は、実装に問題がある可能性がある
ため、修正を進める前にユーザーへ報告する。

### 3.10 page registrationの既知の制約（アンカー選定前に必読）

`src/phase6/page_registration.py`の位置合わせアルゴリズムには、実画像でアンカーを
選ぶ前に理解しておくべき既知の制約がある。

- 現在の登録アルゴリズムは、グレースケール画素の平均絶対誤差（MAE）による
  総当たりの平行移動探索である。回転・拡大縮小・照明正規化は行わない。
- 大きな単色四角形のような**特徴の少ないアンカー**では、探索範囲外にある真の位置
  ではなく、探索範囲境界付近の位置でも、部分的な重なりだけで高いスコアを
  出してしまう場合があることが合成テストで確認されている
  （`tests/phase6/test_page_registration.py`の
  `test_shift_just_beyond_search_range_can_still_score_high_known_limitation`参照。
  既知の限界として意図的に固定してあり、閾値やアルゴリズムを調整して隠していない）。
- そのため、実帳票のアンカーには、単色領域ではなく、**罫線の交点・固定印刷文字・
  複数のエッジを含む識別性の高い印刷済みパターン**を選ぶこと（例: 表の罫線交差部、
  「AU1K」等の固定印字部分の輪郭）。
- 実画像を確認する前にアンカー座標・セル座標を決めないこと（停止条件4と同じ）。
- この制約を覆い隠すための閾値調整・ページ別の例外処理は行わないこと
  （実データの期待値に合わせたパラメータ調整はしない。停止条件6と同じ精神）。

### 3.11〜3.14 P59実画像検証（v3用runnerの作成が前提。3.15参照）

1. P59の実画像を目視確認する。**この時点で初めて**、3.10節の制約を踏まえて
   アンカーテンプレート（`page_registration.AnchorTemplate`）の座標と、
   `CellRegionPair`/`StoreCodeRegionPair`の実際の座標を決定する（停止条件4）。
2. 対象は**P59のみ**とする。P32・P41・P66は、P59が正式に通るまで実行しない
   （停止条件5）。
3. 期待値（1節記載のP59確定事項：intro written_total=0、
   intro tally=no_marks_observed）と実行結果を比較する。
4. 合わない場合は、同一バージョン内で座標調整・再実行を繰り返さず、原因
   （位置合わせの精度・領域座標・プロンプト・契約のいずれか）を切り分けて報告する
   （停止条件6）。

### 3.15 v3用実行スクリプトについて（重要）

**v3の実画像検証を実行するCLIスクリプトは、このセッション時点でまだ作成していない。**
`src/phase6/vision_evidence_client_v3.py`の`run_vision_evidence_pilot_page_v3()`は
ライブラリ関数として実装・合成テスト済みだが、これを実際にPDFページ画像へ適用し
実Anthropicクライアントで呼び出す薄いCLIスクリプト（v2でいう
`scripts/run_phase6_vision_evidence_pilot.py`に相当するもの）はまだ存在しない。

- v2の`scripts/run_phase6_vision_evidence_pilot.py`をv3の代わりに使わないこと
  （停止条件7）。v2はregionベース・PDF直接読み込みの別実装であり、v3の
  registrationゲート・cell構造とは互換性がない。
- v3用runnerの作成は、**P59の実画像を確認した後に、別作業として**行うこと（本手順書の
  スコープ外）。実画像を見る前に座標を決め打ちしたrunnerを先に作らない。

---

## 4. このドキュメントのスコープ外

- Step 4（三者比較）・Step 5（review routing）の再開（`stash@{0}`）。
- `reconciliation.py`の`Any`エラー修正。
- v3用CLI runnerの実装そのもの（3.15節の通り、P59実画像確認後の別作業）。
- API呼び出し・実データでの回帰テストの実施そのもの（本書は手順の記載のみ）。

"""
合成サンプルPDF × Salesforce CSV 照合ロジック

Phase 4: CSV照合エンジン

フロー：
1. Vision API抽出結果（synthetic_extraction_results.csv）を読込
2. Salesforce想定CSV（salesforce_sample.csv）を読込
3. マッチングキーに基づいて照合
4. ステータス判定（一致/不一致/要確認）
5. 差分を記録
6. 結果CSVとレポート生成

照合ロジックは reconciliation.py に分離済み
このファイルはテスト実行専用
"""

from pathlib import Path
from reconciliation import (
    load_extraction_results,
    load_salesforce_csv,
    reconcile,
    output_reconciliation_csv,
    output_reconciliation_report
)

SCRIPT_DIR = Path(__file__).parent
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
SAMPLES_DIR = SCRIPT_DIR / "samples" / "synthetic"


def main():
    """照合ロジックのテスト実行"""

    print("=" * 60)
    print("Phase 4: CSV照合ロジック検証")
    print("=" * 60)

    # Step 1: 抽出結果CSVを読込
    print("\n[1] Vision API抽出結果を読込中...")
    extraction_results = load_extraction_results(
        OUTPUTS_DIR / "synthetic_extraction_results.csv"
    )
    print(f"[OK] {len(extraction_results)}件の抽出結果を読込完了")

    # Step 2: Salesforce CSVを読込
    print("\n[2] Salesforce CSVを読込中...")
    salesforce_records = load_salesforce_csv(
        SAMPLES_DIR / "salesforce_sample.csv"
    )
    print(f"[OK] {len(salesforce_records)}件のSalesforceレコードを読込完了")

    # Step 3: 照合実行
    print("\n[3] 照合処理を実行中...")
    reconciliation_results = []
    for extraction in extraction_results:
        result = reconcile(extraction, salesforce_records)
        reconciliation_results.append(result)

    print(f"[OK] {len(reconciliation_results)}件の照合完了")

    # Step 4: 結果を出力
    print("\n[4] 結果ファイルを生成中...")
    output_reconciliation_csv(reconciliation_results, str(OUTPUTS_DIR / "reconciliation_results.csv"))
    output_reconciliation_report(reconciliation_results, str(OUTPUTS_DIR / "reconciliation_report.md"))
    print("[OK] 出力完了")

    # Step 5: 統計情報を表示
    print("\n" + "=" * 60)
    print("照合結果サマリー")
    print("=" * 60)

    status_counts = {}
    for result in reconciliation_results:
        status = result.status
        status_counts[status] = status_counts.get(status, 0) + 1

    total = len(reconciliation_results)
    print(f"総照合対象件数: {total}件\n")

    for status, count in sorted(status_counts.items()):
        percentage = (count / total) * 100
        print(f"  {status}: {count}件 ({percentage:.1f}%)")

    # マッチング成功率
    csv_match_success = sum(1 for r in reconciliation_results
                           if r.matching_key != "見つかりませんでした")
    if csv_match_success > 0 or total > 0:
        success_rate = (csv_match_success / total) * 100
        print(f"\nCSV行特定成功: {csv_match_success}/{total}件 ({success_rate:.1f}%)")

    print("\n[COMPLETE] テスト実行完了")


if __name__ == "__main__":
    main()

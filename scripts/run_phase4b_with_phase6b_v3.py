"""
Phase 4b Field Comparison with Phase 6B v3 Extraction Results

Reads phase6b_30pages_results_v3.json and outputs v3 comparison files.
"""

import json
import sys
import pandas as pd
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from reconciliation_phase1 import Phase1ReconciliationEngine

EXTRACTION_RESULT_PATH = PROJECT_ROOT / "data/test_outputs/phase6b_30pages_results_v3.json"
CSV_PATH = PROJECT_ROOT / "tests/fixtures/geo_pdf_reconciliation/report1780043296399.csv"
STORE_MAPPING_PATH = PROJECT_ROOT / "data/master/store_code_mapping.csv"
STAFF_MASTER_PATH = PROJECT_ROOT / "data/master/staff_name_master.csv"
FIELD_MAPPING_PATH = PROJECT_ROOT / "data/master/pdf_csv_field_mapping.csv"
OUTPUT_DIR = PROJECT_ROOT / "data/test_outputs"

TARGET_DATE = '2026/05/17'


def load_extraction_results():
    with open(EXTRACTION_RESULT_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    details = data['details']
    by_page = defaultdict(lambda: {'mapped_values': {}})

    for d in details:
        page = d['page']
        region = d['region']
        item = d['item']
        value = d['value']
        status = d['status']

        if region == 'basic_info_header':
            by_page[page][item] = value
        elif region == 'basic_info_footer':
            by_page[page][item] = value
        else:
            if status == 'success' and value is not None:
                by_page[page]['mapped_values'][item] = value
            elif status == 'uncertain':
                by_page[page]['mapped_values'][item] = 'uncertain'

    pdf_records = []
    for page_no in sorted(by_page.keys()):
        page_data = by_page[page_no]
        pdf_record = {
            'page_no': page_no,
            'store_name': page_data.get('store_name'),
            'staff_name': page_data.get('staff_name'),
            'data_no': page_data.get('data_no'),
            'tablet_no': page_data.get('tablet_no'),
            'mapped_values': page_data.get('mapped_values', {}),
        }
        pdf_records.append(pdf_record)

    return pdf_records


def main():
    print("=" * 100)
    print("PHASE 4B v3: FIELD COMPARISON WITH PHASE 6B v3 EXTRACTION")
    print("=" * 100)
    print()

    csv_df = pd.read_csv(CSV_PATH, encoding='cp932')
    store_master = pd.read_csv(STORE_MAPPING_PATH, encoding='utf-8')
    staff_master = pd.read_csv(STAFF_MASTER_PATH, encoding='utf-8')
    field_mapping = pd.read_csv(FIELD_MAPPING_PATH, encoding='utf-8')
    pdf_records = load_extraction_results()

    print(f"  PDF records: {len(pdf_records)} pages")
    print(f"  Target date: {TARGET_DATE}")
    print()

    engine = Phase1ReconciliationEngine(
        mapping_table=field_mapping,
        store_master=store_master,
        staff_master=staff_master
    )

    all_results = []
    all_field_comparisons = []
    all_mismatches = []

    stats = {
        'total_pages': len(pdf_records),
        'store_code_found': 0,
        'store_code_not_found': 0,
        'csv_single': 0,
        'csv_multiple': 0,
        'csv_none': 0,
        'status_match': 0,
        'status_mismatch': 0,
        'status_review': 0,
        'field_total': 0,
        'field_compared': 0,
        'field_matched': 0,
        'field_mismatched': 0,
        'field_skipped_pdf_null': 0,
        'field_skipped_pdf_uncertain': 0,
        'field_skipped_csv_null': 0,
        'field_skipped_no_csv_column': 0,
    }

    for pdf_record in pdf_records:
        page_no = pdf_record['page_no']

        result = engine.reconcile_pdf_with_csv(
            pdf_record=pdf_record,
            csv_target=csv_df,
            target_date=TARGET_DATE
        )

        if result.get('store_code'):
            stats['store_code_found'] += 1
        else:
            stats['store_code_not_found'] += 1

        csv_count = result.get('csv_candidate_count', 0)
        if csv_count == 1:
            stats['csv_single'] += 1
        elif csv_count and csv_count > 1:
            stats['csv_multiple'] += 1
        else:
            stats['csv_none'] += 1

        status = result.get('status', 'review')
        if status == 'match':
            stats['status_match'] += 1
        elif status == 'mismatch':
            stats['status_mismatch'] += 1
        else:
            stats['status_review'] += 1

        field_comparisons = result.get('field_comparisons', [])
        summary = result.get('field_comparison_summary', {})

        if summary:
            stats['field_total'] += summary.get('total_fields', 0)
            stats['field_compared'] += summary.get('compared_fields', 0)
            stats['field_matched'] += summary.get('matched_fields', 0)
            stats['field_mismatched'] += summary.get('mismatched_fields', 0)

        for fc in field_comparisons:
            fc_record = {
                'page_number': page_no,
                'pdf_store_name': result.get('pdf_store_name', ''),
                'mapped_store_code': result.get('store_code', ''),
                'fax_item_name': fc.get('fax_item_name', ''),
                'csv_column_code': fc.get('csv_column_code', ''),
                'csv_column_name': fc.get('csv_column_name', ''),
                'pdf_value': fc.get('pdf_value'),
                'csv_value': fc.get('csv_value'),
                'comparison_status': fc.get('comparison_status', ''),
                'reason': fc.get('reason', ''),
            }
            all_field_comparisons.append(fc_record)

            comp_status = fc.get('comparison_status', '')
            if comp_status == 'skipped_pdf_null':
                stats['field_skipped_pdf_null'] += 1
            elif comp_status == 'skipped_pdf_uncertain':
                stats['field_skipped_pdf_uncertain'] += 1
            elif comp_status == 'skipped_csv_null':
                stats['field_skipped_csv_null'] += 1
            elif comp_status == 'skipped_no_csv_column':
                stats['field_skipped_no_csv_column'] += 1

            if comp_status == 'mismatch':
                all_mismatches.append(fc_record)

        page_result = {
            'page_number': page_no,
            'pdf_store_name': result.get('pdf_store_name', ''),
            'mapped_store_code': result.get('store_code', ''),
            'store_name': result.get('store_name', ''),
            'staff_name': result.get('staff_name', ''),
            'data_no': result.get('data_no', ''),
            'tablet_no': result.get('tablet_no', ''),
            'status': status,
            'match_status': result.get('match_status', ''),
            'csv_candidate_count': csv_count if csv_count else 0,
            'match_count': result.get('match_count', 0),
            'diff_count': result.get('diff_count', 0),
            'unreadable_count': result.get('unreadable_count', 0),
            'score': result.get('score', 0),
            'review_reasons': '; '.join(result.get('review_reasons', [])),
            'warnings': '; '.join(result.get('warnings', [])),
            'total_fields': summary.get('total_fields', 0) if summary else 0,
            'compared_fields': summary.get('compared_fields', 0) if summary else 0,
            'matched_fields': summary.get('matched_fields', 0) if summary else 0,
            'mismatched_fields': summary.get('mismatched_fields', 0) if summary else 0,
            'match_rate': summary.get('match_rate', 0) if summary else 0,
        }
        all_results.append(page_result)

        if (page_no + 1) % 10 == 0:
            print(f"  Processed {page_no + 1}/30 pages")

    print(f"  Processed all {len(pdf_records)} pages")
    print()

    # Summary
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print()
    print(f"Store code: {stats['store_code_found']}/30 found")
    print(f"CSV single: {stats['csv_single']}/30, multiple: {stats['csv_multiple']}/30, none: {stats['csv_none']}/30")
    print(f"Status: match={stats['status_match']}, mismatch={stats['status_mismatch']}, review={stats['status_review']}")
    print()
    print(f"Field comparisons:")
    print(f"  Compared: {stats['field_compared']}")
    print(f"  Matched:  {stats['field_matched']}")
    print(f"  Mismatch: {stats['field_mismatched']}")
    print(f"  skipped_pdf_null:     {stats['field_skipped_pdf_null']}")
    print(f"  skipped_pdf_uncertain:{stats['field_skipped_pdf_uncertain']}")
    print(f"  skipped_csv_null:     {stats['field_skipped_csv_null']}")

    if stats['field_compared'] > 0:
        match_rate = stats['field_matched'] / stats['field_compared'] * 100
        print(f"  Match rate: {stats['field_matched']}/{stats['field_compared']} = {match_rate:.1f}%")
    print()
    print(f"Mismatches: {len(all_mismatches)}")

    # Save
    df_pages = pd.DataFrame(all_results)
    df_pages.to_csv(OUTPUT_DIR / "phase6b_v3_reconciliation_page_summary.csv", index=False, encoding='utf-8-sig')
    print(f"Saved: phase6b_v3_reconciliation_page_summary.csv ({len(df_pages)} rows)")

    df_fields = pd.DataFrame(all_field_comparisons)
    df_fields.to_csv(OUTPUT_DIR / "phase6b_v3_reconciliation_field_comparisons.csv", index=False, encoding='utf-8-sig')
    print(f"Saved: phase6b_v3_reconciliation_field_comparisons.csv ({len(df_fields)} rows)")

    df_mismatch = pd.DataFrame(all_mismatches)
    df_mismatch.to_csv(OUTPUT_DIR / "phase6b_v3_reconciliation_mismatch_list.csv", index=False, encoding='utf-8-sig')
    print(f"Saved: phase6b_v3_reconciliation_mismatch_list.csv ({len(df_mismatch)} rows)")

    summary_json = {
        'timestamp': datetime.now().isoformat(),
        'version': 'v3',
        'target_date': TARGET_DATE,
        'stats': stats,
        'mismatch_count': len(all_mismatches),
        'mismatches': all_mismatches[:20],
    }
    with open(OUTPUT_DIR / "phase6b_v3_reconciliation_summary.json", 'w', encoding='utf-8') as f:
        json.dump(summary_json, f, ensure_ascii=False, indent=2, default=str)
    print(f"Saved: phase6b_v3_reconciliation_summary.json")


if __name__ == "__main__":
    main()

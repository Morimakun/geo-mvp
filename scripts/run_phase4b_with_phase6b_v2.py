"""
Phase 4b Field Comparison with Phase 6B v2 Extraction Results

Uses the EXISTING Phase1ReconciliationEngine directly.
Feeds Phase 6B v2 extraction results into it.

Key integration points:
- Phase 6B v2 extraction → pdf_record format for Phase 1
- target_date = '2026/05/17' (fixed for this batch)
- store_name partial matching is handled by Phase 1's _find_store_code()
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

# Paths
EXTRACTION_RESULT_PATH = PROJECT_ROOT / "data/test_outputs/phase6b_30pages_results.json"
CSV_PATH = PROJECT_ROOT / "tests/fixtures/geo_pdf_reconciliation/report1780043296399.csv"
STORE_MAPPING_PATH = PROJECT_ROOT / "data/master/store_code_mapping.csv"
STAFF_MASTER_PATH = PROJECT_ROOT / "data/master/staff_name_master.csv"
FIELD_MAPPING_PATH = PROJECT_ROOT / "data/master/pdf_csv_field_mapping.csv"
OUTPUT_DIR = PROJECT_ROOT / "data/test_outputs"

TARGET_DATE = '2026/05/17'


def load_extraction_results():
    """Load Phase 6B v2 extraction results and convert to pdf_record format."""
    with open(EXTRACTION_RESULT_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    details = data['details']

    # Organize by page
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
            # case_items, existing_support, new_options → mapped_values
            if status == 'success' and value is not None:
                by_page[page]['mapped_values'][item] = value
            elif status == 'uncertain':
                by_page[page]['mapped_values'][item] = 'uncertain'
            # null → don't add (will be skipped_pdf_null)

    # Convert to Phase 1 pdf_record format
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
    print("PHASE 4B: FIELD COMPARISON WITH PHASE 6B V2 EXTRACTION")
    print("Using existing Phase1ReconciliationEngine")
    print("=" * 100)
    print()

    # Load data
    print("Loading data...")
    csv_df = pd.read_csv(CSV_PATH, encoding='cp932')
    store_master = pd.read_csv(STORE_MAPPING_PATH, encoding='utf-8')
    staff_master = pd.read_csv(STAFF_MASTER_PATH, encoding='utf-8')
    field_mapping = pd.read_csv(FIELD_MAPPING_PATH, encoding='utf-8')
    pdf_records = load_extraction_results()

    print(f"  CSV: {len(csv_df)} rows, {len(csv_df.columns)} cols")
    print(f"  Store master: {len(store_master)} entries")
    print(f"  Staff master: {len(staff_master)} entries")
    print(f"  Field mapping: {len(field_mapping)} entries")
    print(f"  PDF records: {len(pdf_records)} pages")
    print(f"  Target date: {TARGET_DATE}")
    print()

    # Initialize Phase 1 engine
    engine = Phase1ReconciliationEngine(
        mapping_table=field_mapping,
        store_master=store_master,
        staff_master=staff_master
    )

    print(f"  Confirmed mapping items: {len(engine.confirmed_mapping)}")
    print()

    # Run reconciliation for each page
    print("=" * 100)
    print("RUNNING RECONCILIATION")
    print("=" * 100)
    print()

    all_results = []
    all_field_comparisons = []
    all_mismatches = []

    # Aggregate stats
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

        # Call Phase 1 engine
        result = engine.reconcile_pdf_with_csv(
            pdf_record=pdf_record,
            csv_target=csv_df,
            target_date=TARGET_DATE
        )

        # Track stats
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

        # Track field comparisons
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

            # Track skipped reasons
            comp_status = fc.get('comparison_status', '')
            if comp_status == 'skipped_pdf_null':
                stats['field_skipped_pdf_null'] += 1
            elif comp_status == 'skipped_pdf_uncertain':
                stats['field_skipped_pdf_uncertain'] += 1
            elif comp_status == 'skipped_csv_null':
                stats['field_skipped_csv_null'] += 1
            elif comp_status == 'skipped_no_csv_column':
                stats['field_skipped_no_csv_column'] += 1

            # Track mismatches
            if comp_status == 'mismatch':
                all_mismatches.append(fc_record)

        # Page summary
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

    print(f"Total pages: {stats['total_pages']}")
    print()
    print("Store code conversion:")
    print(f"  Found: {stats['store_code_found']}/30 ({stats['store_code_found']/30*100:.1f}%)")
    print(f"  Not found: {stats['store_code_not_found']}/30")
    print()
    print("CSV candidate matching:")
    print(f"  Single (ready): {stats['csv_single']}/30")
    print(f"  Multiple: {stats['csv_multiple']}/30")
    print(f"  None: {stats['csv_none']}/30")
    print()
    print("Final status:")
    print(f"  match: {stats['status_match']}/30")
    print(f"  mismatch: {stats['status_mismatch']}/30")
    print(f"  review: {stats['status_review']}/30")
    print()
    print("Field comparisons:")
    print(f"  Total fields: {stats['field_total']}")
    print(f"  Compared: {stats['field_compared']}")
    print(f"  Matched: {stats['field_matched']}")
    print(f"  Mismatched: {stats['field_mismatched']}")
    print(f"  skipped_pdf_null: {stats['field_skipped_pdf_null']}")
    print(f"  skipped_pdf_uncertain: {stats['field_skipped_pdf_uncertain']}")
    print(f"  skipped_csv_null: {stats['field_skipped_csv_null']}")
    print(f"  skipped_no_csv_column: {stats['field_skipped_no_csv_column']}")

    if stats['field_compared'] > 0:
        match_rate = stats['field_matched'] / stats['field_compared'] * 100
        print(f"  Match rate: {stats['field_matched']}/{stats['field_compared']} = {match_rate:.1f}%")
    print()

    print(f"Mismatches: {len(all_mismatches)}")
    if all_mismatches:
        print("Top mismatches:")
        for m in all_mismatches[:10]:
            print(f"  Page {m['page_number']}: {m['fax_item_name']} ({m['csv_column_code']}) PDF={m['pdf_value']} vs CSV={m['csv_value']}")
    print()

    # Save outputs
    print("=" * 100)
    print("SAVING OUTPUTS")
    print("=" * 100)
    print()

    # 1. Page summary
    df_pages = pd.DataFrame(all_results)
    pages_path = OUTPUT_DIR / "phase6b_v2_reconciliation_page_summary.csv"
    df_pages.to_csv(pages_path, index=False, encoding='utf-8-sig')
    print(f"Saved: {pages_path.name} ({len(df_pages)} rows)")

    # 2. Field comparisons
    df_fields = pd.DataFrame(all_field_comparisons)
    fields_path = OUTPUT_DIR / "phase6b_v2_reconciliation_field_comparisons.csv"
    df_fields.to_csv(fields_path, index=False, encoding='utf-8-sig')
    print(f"Saved: {fields_path.name} ({len(df_fields)} rows)")

    # 3. Mismatch list
    df_mismatch = pd.DataFrame(all_mismatches)
    mismatch_path = OUTPUT_DIR / "phase6b_v2_reconciliation_mismatch_list.csv"
    df_mismatch.to_csv(mismatch_path, index=False, encoding='utf-8-sig')
    print(f"Saved: {mismatch_path.name} ({len(df_mismatch)} rows)")

    # 4. Store master review items (no_match pages)
    no_match_pages = [r for r in all_results if r['csv_candidate_count'] == 0 and not r['mapped_store_code']]
    store_review = []
    for r in no_match_pages:
        store_review.append({
            'page_number': r['page_number'],
            'pdf_store_name': r['pdf_store_name'],
            'possible_reason': 'store_code_mapping.csv not found',
            'suggested_action': 'Confirm with Katayama-san; add to master if confirmed',
        })
    df_store_review = pd.DataFrame(store_review)
    store_review_path = OUTPUT_DIR / "phase6b_v2_store_master_review_items.csv"
    df_store_review.to_csv(store_review_path, index=False, encoding='utf-8-sig')
    print(f"Saved: {store_review_path.name} ({len(df_store_review)} rows)")

    # 5. Multiple candidate review items
    multi_pages = [r for r in all_results if r['csv_candidate_count'] > 1]
    multi_review = []
    for r in multi_pages:
        multi_review.append({
            'page_number': r['page_number'],
            'pdf_store_name': r['pdf_store_name'],
            'mapped_store_code': r['mapped_store_code'],
            'candidate_count': r['csv_candidate_count'],
            'review_reason': r['review_reasons'],
        })
    df_multi_review = pd.DataFrame(multi_review)
    multi_review_path = OUTPUT_DIR / "phase6b_v2_multiple_candidate_review_items.csv"
    df_multi_review.to_csv(multi_review_path, index=False, encoding='utf-8-sig')
    print(f"Saved: {multi_review_path.name} ({len(df_multi_review)} rows)")

    # 6. Download CSV (all-in-one for Phase 4b UI)
    download_records = []
    for r in all_results:
        download_records.append({
            'page': r['page_number'],
            'store_name': r['pdf_store_name'],
            'store_code': r['mapped_store_code'],
            'staff_name': r['staff_name'],
            'data_no': r['data_no'],
            'tablet_no': r['tablet_no'],
            'status': r['status'],
            'csv_candidates': r['csv_candidate_count'],
            'match_count': r['match_count'],
            'diff_count': r['diff_count'],
            'total_fields': r['total_fields'],
            'compared_fields': r['compared_fields'],
            'matched_fields': r['matched_fields'],
            'mismatched_fields': r['mismatched_fields'],
            'match_rate': r['match_rate'],
            'review_reasons': r['review_reasons'],
        })
    df_download = pd.DataFrame(download_records)
    download_path = OUTPUT_DIR / "phase6b_v2_reconciliation_download.csv"
    df_download.to_csv(download_path, index=False, encoding='utf-8-sig')
    print(f"Saved: {download_path.name} ({len(df_download)} rows)")

    # 7. Summary JSON
    summary_json = {
        'timestamp': datetime.now().isoformat(),
        'target_date': TARGET_DATE,
        'stats': stats,
        'mismatch_count': len(all_mismatches),
        'mismatches': all_mismatches[:20],
    }
    summary_json_path = OUTPUT_DIR / "phase6b_v2_reconciliation_summary_final.json"
    with open(summary_json_path, 'w', encoding='utf-8') as f:
        json.dump(summary_json, f, ensure_ascii=False, indent=2, default=str)
    print(f"Saved: {summary_json_path.name}")


if __name__ == "__main__":
    main()

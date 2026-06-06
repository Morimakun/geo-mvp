"""
Phase 6B v2 Reconciliation - WITH DATE MATCHING FIX

Key fix: Use target_date to filter CSV rows BEFORE matching store_code
This should reduce multiple candidates from 23 to ~4-5
"""

import json
import pandas as pd
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
EXTRACTION_RESULT_PATH = PROJECT_ROOT / "data/test_outputs/phase6b_30pages_results.json"
CSV_PATH = PROJECT_ROOT / "tests/fixtures/geo_pdf_reconciliation/report1780043296399.csv"
STORE_MAPPING_PATH = PROJECT_ROOT / "data/master/store_code_mapping.csv"
OUTPUT_DIR = PROJECT_ROOT / "data/test_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ASSUMPTION: All 30 PDF pages are from 2026/05/17 or 2026/05/18
# We'll test both dates
TARGET_DATES = ['2026/05/17', '2026/05/18']  # Will try both

def load_data():
    """Load data."""
    with open(EXTRACTION_RESULT_PATH, 'r', encoding='utf-8') as f:
        extraction_details = json.load(f)['details']

    csv_df = pd.read_csv(CSV_PATH, encoding='cp932')
    store_mapping = pd.read_csv(STORE_MAPPING_PATH, encoding='utf-8')

    return extraction_details, csv_df, store_mapping

def organize_by_page(details):
    """Organize extraction by page."""
    by_page = defaultdict(dict)
    for d in details:
        page = d['page']
        region = d['region']
        item = d['item']
        value = d['value']

        if region == 'basic_info_header':
            by_page[page][item] = value
        elif region == 'basic_info_footer':
            by_page[page][item] = value

    return dict(by_page)

def convert_store_code(store_name, store_mapping):
    """Convert PDF store name to store code."""
    if not store_name:
        return None, 'no_pdf_value'

    # Try exact match
    for _, row in store_mapping.iterrows():
        if row['store_name'] == store_name:
            return row['store_code'], 'exact_match'

    return None, 'not_found'

def find_csv_candidates_with_date(store_code, target_date, csv_df):
    """Find CSV rows matching store_code AND target_date (proper Phase 2 logic)."""
    if not store_code:
        return [], []

    store_code_col = csv_df.columns[280]  # Column 281: store code
    date_col = csv_df.columns[282]  # Column 283: 営業日

    # FILTER BY DATE FIRST (this is what Phase 2 should do)
    csv_by_date = csv_df[csv_df[date_col] == target_date]

    # THEN FILTER BY STORE CODE
    candidates = csv_by_date[csv_by_date[store_code_col] == store_code]

    return candidates.to_dict('records'), candidates.index.tolist()

def main():
    print("=" * 100)
    print("PHASE 6B V2 RECONCILIATION WITH DATE MATCHING FIX")
    print("=" * 100)
    print()

    extraction_details, csv_df, store_mapping = load_data()
    by_page = organize_by_page(extraction_details)

    print(f"CSV date column (col 283): {csv_df.columns[282]}")
    print(f"Unique dates in CSV: {csv_df[csv_df.columns[282]].unique().tolist()}")
    print()

    store_code_col = csv_df.columns[280]
    date_col = csv_df.columns[282]

    # Test both dates
    results_by_date = {}

    for target_date in TARGET_DATES:
        print(f"\n{'='*100}")
        print(f"TESTING WITH TARGET_DATE = {target_date}")
        print(f"{'='*100}")

        csv_by_date = csv_df[csv_df[date_col] == target_date]
        print(f"CSV rows for {target_date}: {len(csv_by_date)}/43")
        print()

        page_results = []
        stats = {
            'single_candidate': 0,
            'multiple_candidates': 0,
            'no_candidates': 0,
            'store_code_success': 0,
            'store_code_failed': 0,
        }

        print("Processing pages...")
        for page_no in sorted(by_page.keys()):
            page_data = by_page[page_no]
            store_name = page_data.get('store_name')

            # Convert store code
            store_code, conversion_status = convert_store_code(store_name, store_mapping)

            if store_code:
                stats['store_code_success'] += 1
            else:
                stats['store_code_failed'] += 1

            # Find candidates (with date filtering)
            candidates, candidate_indices = find_csv_candidates_with_date(
                store_code, target_date, csv_df
            )

            candidate_count = len(candidates)
            if candidate_count == 1:
                stats['single_candidate'] += 1
            elif candidate_count > 1:
                stats['multiple_candidates'] += 1
            else:
                stats['no_candidates'] += 1

            page_result = {
                'page': page_no,
                'store_name': store_name,
                'store_code': store_code,
                'conversion_status': conversion_status,
                'candidate_count': candidate_count,
                'candidate_indices': candidate_indices,
            }
            page_results.append(page_result)

            if (page_no + 1) % 10 == 0:
                print(f"  Processed {page_no + 1}/30 pages")

        print()
        print(f"RESULTS FOR {target_date}:")
        print(f"  Store code conversion: {stats['store_code_success']}/30")
        print(f"  Single candidate: {stats['single_candidate']}/30")
        print(f"  Multiple candidates: {stats['multiple_candidates']}/30")
        print(f"  No candidates: {stats['no_candidates']}/30")
        print()

        results_by_date[target_date] = {
            'stats': stats,
            'page_results': page_results,
        }

    # Save best result
    print()
    print("=" * 100)
    print("SUMMARY AND RECOMMENDATION")
    print("=" * 100)
    print()

    # Choose best date (the one with most single candidates)
    best_date = max(
        results_by_date.keys(),
        key=lambda d: results_by_date[d]['stats']['single_candidate']
    )

    best_result = results_by_date[best_date]
    print(f"Best match date: {best_date}")
    print(f"  Single candidates: {best_result['stats']['single_candidate']}/30")
    print(f"  Multiple candidates: {best_result['stats']['multiple_candidates']}/30")
    print(f"  No candidates: {best_result['stats']['no_candidates']}/30")
    print()

    # Save results for best date
    df_results = pd.DataFrame(best_result['page_results'])
    output_path = OUTPUT_DIR / "phase6b_v2_reconciliation_with_date_fix.csv"
    df_results.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"Saved: {output_path.name}")

    # Save summary
    summary_json = {
        'target_date': best_date,
        'stats': best_result['stats'],
        'all_results': {
            d: {
                'single_candidate': results_by_date[d]['stats']['single_candidate'],
                'multiple_candidates': results_by_date[d]['stats']['multiple_candidates'],
                'no_candidates': results_by_date[d]['stats']['no_candidates'],
            }
            for d in results_by_date.keys()
        },
    }

    summary_path = OUTPUT_DIR / "phase6b_v2_date_fix_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary_json, f, ensure_ascii=False, indent=2)
    print(f"Saved: {summary_path.name}")

    print()
    print("NEXT: If single_candidate >= 20, can proceed to Phase 4b field comparisons")

if __name__ == "__main__":
    main()

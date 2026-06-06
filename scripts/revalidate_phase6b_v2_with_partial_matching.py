"""
Phase 6B v2 Reconciliation - WITH PARTIAL NAME MATCHING

Key fix: PDF store names (short form) must be matched against
Master store names (long form with company prefix)

Example:
  PDF:    「ニトリ 五日市」
  Master: 「ニトリショップ@ニトリ 五日市」
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

TARGET_DATE = '2026/05/17'  # From earlier analysis

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

        if region in ['basic_info_header', 'basic_info_footer']:
            by_page[page][item] = value

    return dict(by_page)

def convert_store_code_with_partial_match(store_name, store_mapping):
    """Convert PDF store name to store code with PARTIAL MATCHING.

    PDF names are short form (e.g., 「ニトリ 五日市」)
    Master names are long form (e.g., 「ニトリショップ@ニトリ 五日市」)

    Strategy: Find master rows where the short name is contained in the long name
    """
    if not store_name:
        return None, 'no_pdf_value', None

    # Try exact match first
    for _, row in store_mapping.iterrows():
        if row['store_name'] == store_name:
            return row['store_code'], 'exact_match', row['store_name']

    # Try partial match: look for rows containing the PDF store name
    candidates = []
    for _, row in store_mapping.iterrows():
        if store_name in row['store_name']:
            candidates.append((row['store_code'], row['store_name']))

    if len(candidates) == 1:
        code, master_name = candidates[0]
        return code, 'partial_match', master_name
    elif len(candidates) > 1:
        # Multiple matches - need more disambigation
        return None, 'ambiguous_match', None
    else:
        return None, 'not_found', None

def find_csv_candidates_with_date(store_code, target_date, csv_df):
    """Find CSV rows matching store_code AND target_date."""
    if not store_code:
        return [], []

    store_code_col = csv_df.columns[280]
    date_col = csv_df.columns[282]

    # Filter by date, then by store_code
    csv_by_date = csv_df[csv_df[date_col] == target_date]
    candidates = csv_by_date[csv_by_date[store_code_col] == store_code]

    return candidates.to_dict('records'), candidates.index.tolist()

def main():
    print("=" * 100)
    print("PHASE 6B V2 RECONCILIATION WITH PARTIAL NAME MATCHING AND DATE FILTERING")
    print("=" * 100)
    print()

    extraction_details, csv_df, store_mapping = load_data()
    by_page = organize_by_page(extraction_details)

    print(f"Target date: {TARGET_DATE}")
    print(f"CSV rows for {TARGET_DATE}: {len(csv_df[csv_df[csv_df.columns[282]] == TARGET_DATE])}/43")
    print()

    store_code_col = csv_df.columns[280]
    date_col = csv_df.columns[282]

    page_results = []
    stats = {
        'total_pages': len(by_page),
        'store_code_exact_match': 0,
        'store_code_partial_match': 0,
        'store_code_ambiguous': 0,
        'store_code_not_found': 0,
        'csv_single_candidate': 0,
        'csv_multiple_candidates': 0,
        'csv_no_candidates': 0,
    }

    print("Processing pages...")
    for page_no in sorted(by_page.keys()):
        page_data = by_page[page_no]
        store_name = page_data.get('store_name')

        # Convert store code with partial matching
        store_code, conversion_status, matched_master_name = convert_store_code_with_partial_match(
            store_name, store_mapping
        )

        # Track conversion status
        if conversion_status == 'exact_match':
            stats['store_code_exact_match'] += 1
        elif conversion_status == 'partial_match':
            stats['store_code_partial_match'] += 1
        elif conversion_status == 'ambiguous_match':
            stats['store_code_ambiguous'] += 1
        else:
            stats['store_code_not_found'] += 1

        # Find candidates with date filtering
        candidates, candidate_indices = find_csv_candidates_with_date(
            store_code, TARGET_DATE, csv_df
        )

        candidate_count = len(candidates)
        if candidate_count == 1:
            stats['csv_single_candidate'] += 1
        elif candidate_count > 1:
            stats['csv_multiple_candidates'] += 1
        else:
            stats['csv_no_candidates'] += 1

        page_result = {
            'page': page_no,
            'pdf_store_name': store_name,
            'matched_master_name': matched_master_name,
            'store_code': store_code,
            'conversion_status': conversion_status,
            'csv_candidate_count': candidate_count,
            'csv_row_indices': candidate_indices,
            'status': (
                'ready_for_comparison' if candidate_count == 1 else (
                    'needs_disambiguation' if candidate_count > 1 else 'no_match'
                )
            ),
        }
        page_results.append(page_result)

        if (page_no + 1) % 10 == 0:
            print(f"  Processed {page_no + 1}/30 pages")

    print()
    print("=" * 100)
    print("RESULTS")
    print("=" * 100)
    print()

    print("Store code conversion:")
    print(f"  Exact match: {stats['store_code_exact_match']}/30")
    print(f"  Partial match: {stats['store_code_partial_match']}/30")
    print(f"  Ambiguous match: {stats['store_code_ambiguous']}/30")
    print(f"  Not found: {stats['store_code_not_found']}/30")
    print()

    print("CSV candidate matching (with date filtering):")
    print(f"  Single candidate (READY): {stats['csv_single_candidate']}/30")
    print(f"  Multiple candidates: {stats['csv_multiple_candidates']}/30")
    print(f"  No candidates: {stats['csv_no_candidates']}/30")
    print()

    ready_for_comparison = stats['csv_single_candidate']
    print(f"[VERDICT] Pages ready for Phase 4b field comparison: {ready_for_comparison}/30")
    print()

    if ready_for_comparison >= 10:
        print("[OK] Can proceed to Phase 4b with reasonable sample size")
    else:
        print("[WARN] Need more investigation into store name matching")

    # Save results
    df_results = pd.DataFrame(page_results)
    output_path = OUTPUT_DIR / "phase6b_v2_reconciliation_with_name_matching.csv"
    df_results.to_csv(output_path, index=False, encoding='utf-8-sig')
    print()
    print(f"Saved: {output_path.name}")

    # Save summary
    summary_json = {
        'target_date': TARGET_DATE,
        'store_code_conversion': {
            'exact_match': stats['store_code_exact_match'],
            'partial_match': stats['store_code_partial_match'],
            'ambiguous_match': stats['store_code_ambiguous'],
            'not_found': stats['store_code_not_found'],
        },
        'csv_matching': {
            'single_candidate': stats['csv_single_candidate'],
            'multiple_candidates': stats['csv_multiple_candidates'],
            'no_candidates': stats['csv_no_candidates'],
        },
        'ready_for_comparison': ready_for_comparison,
    }

    summary_path = OUTPUT_DIR / "phase6b_v2_name_matching_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary_json, f, ensure_ascii=False, indent=2)
    print(f"Saved: {summary_path.name}")

if __name__ == "__main__":
    main()

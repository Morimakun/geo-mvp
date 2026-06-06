"""
Debug: Inspect date and store_code matching for Phase 6B v2 reconciliation

Checks:
1. Is target_date being passed correctly?
2. What is PDF date (not data_no)?
3. Is CSV date column detected?
4. Is store_code column JU?
5. Why are there 23 multiple candidates?
6. Why are there 3 no_match pages?
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

def load_data():
    """Load all data."""
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

def main():
    print("=" * 100)
    print("DEBUG: DATE AND STORE CODE MATCHING FOR PHASE 6B V2")
    print("=" * 100)
    print()

    extraction_details, csv_df, store_mapping = load_data()
    by_page = organize_by_page(extraction_details)

    print("[STEP 1] CSV STRUCTURE ANALYSIS")
    print("-" * 100)
    print(f"CSV rows: {len(csv_df)}")
    print(f"CSV columns: {len(csv_df.columns)}")
    print()

    # Find store_code column (should be column 281, 0-indexed 280)
    store_code_col = csv_df.columns[280]
    print(f"Store code column (col 281): {store_code_col}")
    print(f"  Sample values: {csv_df[store_code_col].head(3).tolist()}")
    print()

    # Find date columns
    print("Potential date columns in CSV:")
    date_cols = []
    for col in csv_df.columns:
        if any(kw in str(col).lower() for kw in ['date', '日付', '日報', 'business', 'operatin']):
            date_cols.append(col)
            print(f"  {col}: {csv_df[col].head(3).tolist()}")
    print()

    if not date_cols:
        print("[WARN] No date columns detected!")
        print("First few columns:")
        for col in csv_df.columns[:10]:
            print(f"  {col}: {csv_df[col].head(1).tolist()}")
    print()

    # Find JU column (should be commission store code)
    print("Searching for JU-related columns...")
    ju_candidates = []
    for i, col in enumerate(csv_df.columns):
        if 'JU' in str(col).upper() or '被委託' in str(col) or '法人' in str(col):
            ju_candidates.append((i, col))
            print(f"  Col {i}: {col}")
    print()

    print("[STEP 2] PDF EXTRACTION ANALYSIS (First 5 pages)")
    print("-" * 100)

    debug_results = []

    for page_no in sorted(by_page.keys())[:5]:
        page_data = by_page[page_no]

        store_name = page_data.get('store_name')
        data_no = page_data.get('data_no')
        staff_name = page_data.get('staff_name')
        tablet_no = page_data.get('tablet_no')

        print(f"\nPage {page_no}:")
        print(f"  store_name: {store_name!r}")
        print(f"  data_no: {data_no!r} (NOTE: NOT a date field, just a sequence number)")
        print(f"  staff_name: {staff_name!r}")
        print(f"  tablet_no: {tablet_no!r}")

        # Try to find store_code
        store_code = None
        for _, row in store_mapping.iterrows():
            if row['store_name'] == store_name:
                store_code = row['store_code']
                break

        if store_code:
            # Find CSV candidates
            candidates = csv_df[csv_df[store_code_col] == store_code]
            print(f"  Matching store_code: {store_code}")
            print(f"  CSV candidates: {len(candidates)}")

            if len(candidates) > 0:
                print(f"    Candidate row indices: {candidates.index.tolist()}")
                print(f"    Candidate details:")
                for idx in candidates.index:
                    row_dict = candidates.loc[idx]
                    print(f"      Row {idx}:")
                    if date_cols:
                        for date_col in date_cols:
                            print(f"        {date_col}: {row_dict.get(date_col, 'N/A')}")
                    print(f"        {store_code_col}: {row_dict.get(store_code_col, 'N/A')}")
        else:
            print(f"  [NO MATCH] store_name not found in mapping")

        debug_results.append({
            'page': page_no,
            'store_name': store_name,
            'data_no': data_no,
            'store_code': store_code,
            'candidate_count': len(candidates) if store_code else 0,
        })

    print()
    print()
    print("[STEP 3] PROBLEM SUMMARY")
    print("-" * 100)
    print()

    # Analyze why data_no is not a date
    print("ISSUE: Why data_no is NOT a date field")
    print("  data_no appears to be a sequence number (日報 No)")
    print("  It does NOT correspond to any CSV date column")
    print("  We need to find the ACTUAL date field in PDF extraction")
    print()

    print("QUESTION: Is there a date field in Phase 6B extraction?")
    print("  Need to check if PDF extraction includes営業日/business_date")
    print()

    # Check what fields are actually extracted
    print("Fields extracted across all regions:")
    all_fields = set()
    for d in extraction_details:
        all_fields.add((d['region'], d['item']))

    for region in ['basic_info_header', 'basic_info_footer', 'case_items', 'existing_support', 'new_options']:
        region_fields = sorted([item for reg, item in all_fields if reg == region])
        print(f"  {region}: {region_fields}")
    print()

    print("[STEP 4] ROOT CAUSE HYPOTHESIS")
    print("-" * 100)
    print()
    print("Hypothesis: Why 23 pages have multiple candidates")
    print()
    print("1. CSV has multiple rows per store_code (different dates/periods)")
    print("2. PDF extraction does NOT include a date field")
    print("3. The revalidation script uses 'data_no' thinking it's a date, but it's NOT")
    print("4. Without a real date, store_code alone cannot disambiguate CSV rows")
    print("5. Result: 23 pages match multiple CSV rows (the 2 rows per store_code)")
    print()

    print("SOLUTION:")
    print("  A. Add营业日 to Phase 6B extraction (check if PDF has it)")
    print("  B. If no date in PDF, use a fixed date for all 30 pages")
    print("  C. Then Phase 1 logic will properly filter CSV by date + store_code")
    print()

if __name__ == "__main__":
    main()

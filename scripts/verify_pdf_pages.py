#!/usr/bin/env python3
"""
PDF page-by-page extraction verification script
Processes each page of a multi-page PDF as a separate document
"""

import sys
import os
import csv
from pathlib import Path
import fitz  # PyMuPDF
import tempfile
from typing import List, Dict

# Add parent directory to path to import extractor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractor import extract_items_from_pdf


def extract_single_page_as_pdf(input_pdf_path: str, page_num: int) -> bytes:
    """
    Extract a single page from a PDF and return it as a new PDF (bytes)

    Args:
        input_pdf_path: Path to the input PDF file
        page_num: Page number (0-indexed)

    Returns:
        Bytes of the new single-page PDF
    """
    doc = fitz.open(input_pdf_path)

    if page_num >= len(doc):
        raise ValueError(f"Page {page_num} does not exist (PDF has {len(doc)} pages)")

    # Create a new PDF with just this page
    new_doc = fitz.open()
    new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

    # Get PDF bytes
    pdf_bytes = new_doc.write()

    new_doc.close()
    doc.close()

    return pdf_bytes


def process_pdf_pages(pdf_path: str, output_csv: str = None) -> List[Dict]:
    """
    Process all pages of a PDF file

    Args:
        pdf_path: Path to the PDF file
        output_csv: Optional path to output CSV file

    Returns:
        List of extraction results (one per page)
    """
    # Validate input file
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Open PDF to count pages
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    print(f"[PDF] Processing PDF: {os.path.basename(pdf_path)}")
    print(f"      Total pages: {total_pages}")
    print()

    results = []
    successful_pages = 0

    for page_num in range(total_pages):
        try:
            print(f"Processing page {page_num + 1}/{total_pages}...", end=" ")

            # Extract this page as a single-page PDF
            single_page_pdf_bytes = extract_single_page_as_pdf(pdf_path, page_num)

            # Process with extract_items_from_pdf
            page_filename = f"page_{page_num + 1:02d}"
            extraction_result = extract_items_from_pdf(single_page_pdf_bytes, page_filename)

            # Add metadata
            extraction_result['page_number'] = page_num + 1

            # Check success
            has_error = bool(extraction_result.get('error'))
            has_data_no = bool(extraction_result.get('data_no'))
            has_tab_no = bool(extraction_result.get('tab_no'))

            if not has_error and has_data_no and has_tab_no:
                status = "[OK] Success"
                successful_pages += 1
            elif has_error:
                status = f"[ERROR] {extraction_result.get('error', 'Unknown')}"
            else:
                status = "[WARN] Partial (missing DataNo or TabNo)"

            print(status)

            # Remove image from result before storing (too large for CSV)
            if 'pdf_preview' in extraction_result:
                del extraction_result['pdf_preview']

            results.append(extraction_result)

        except Exception as e:
            print(f"[ERROR] Exception: {str(e)}")
            results.append({
                'page_number': page_num + 1,
                'date': None,
                'store': None,
                'name': None,
                'data_no': None,
                'tab_no': None,
                'count': None,
                'total': None,
                'notes': None,
                'left_totals': [],
                'right_totals': [],
                'error': str(e),
                'filename': f"page_{page_num + 1:02d}"
            })

    print()
    print(f"[SUMMARY] {successful_pages}/{total_pages} pages processed successfully")
    print()

    # Output CSV if requested
    if output_csv:
        os.makedirs(os.path.dirname(output_csv) or '.', exist_ok=True)

        csv_headers = [
            'page_number', 'date', 'store', 'name', 'data_no', 'tab_no',
            'count', 'total', 'notes', 'left_totals', 'right_totals', 'error', 'filename'
        ]

        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=csv_headers)
            writer.writeheader()

            for result in results:
                row = {k: result.get(k, '') for k in csv_headers}
                # Convert lists to strings for CSV
                row['left_totals'] = str(row['left_totals']) if row['left_totals'] else ''
                row['right_totals'] = str(row['right_totals']) if row['right_totals'] else ''
                writer.writerow(row)

        print(f"[OK] CSV output saved: {output_csv}")

    return results


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python verify_pdf_pages.py <pdf_path> [output_csv_path]")
        print()
        print("Arguments:")
        print("  pdf_path           : Path to the PDF file to process")
        print("  output_csv_path    : Optional path for CSV output (default: outputs/verification_results.csv)")
        sys.exit(1)

    pdf_path = sys.argv[1]

    # Determine output CSV path
    if len(sys.argv) >= 3:
        output_csv = sys.argv[2]
    else:
        output_csv = os.path.join("outputs", "verification_results.csv")

    try:
        results = process_pdf_pages(pdf_path, output_csv)
        print("[OK] Verification complete")
        return 0
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

import os
import re
import json
import argparse
import time 
import glob

from source.ocr import extract_text


# Maximum pages to scan for DOIs
MAX_PAGES = 100

def extract_doi(ocr_text):
    """
    Finds a DOI pattern in OCR text.
    Pattern: 10.XXXX/anything_until_space_or_end
    """
    match = re.search(r"10\.\d{4}/\S+", ocr_text) 
    if match:
        doi = match.group().rstrip(".,;:)")
        return doi
    return None


def create_doi_link(doi):
    """Creates a full DOI URL."""
    return f"https://doi.org/{doi}" 


def extract_dois(folder_path): 
    """
    Scans the png folder inside the given path, runs OCR on each page,
    and extracts DOIs.

    Args:
        folder_path: Path to journal folder (e.g. "Data/ajil0120no1")

    Returns:
        list: List of dicts with page, fileName, doi, link
    """

    png_folder = os.path.join(folder_path, "png")
    journal_name = os.path.basename(folder_path)

    if not os.path.exists(png_folder):
        print(f"PNG folder not found: {png_folder}")
        return []

    valid_extensions = ('.png', '.jpg', '.jpeg', '.tiff', '.bmp')
    files = sorted([f for f in os.listdir(png_folder) if f.lower().endswith(valid_extensions)])

    total_pages = min(len(files), MAX_PAGES)
    results = []

    print(f"\n{'='*60}")
    print(f"DOI Extraction - {journal_name}")
    print(f"Pages available: {len(files)} | Will scan up to: {total_pages}")
    print(f"{'='*60}\n")

    for i, file_name in enumerate(files[:MAX_PAGES]):

        file_path = os.path.join(png_folder, file_name)

        print(f"\n--- Page {i + 1}/{total_pages} ({file_name}) ---")

        print(f"    Running OCR on {file_name}...")
        ocr_text = extract_text(file_path, preprocess=True)

        if not ocr_text.strip():
            print(f"    OCR returned empty text. Skipping page.")
            continue

        # Extract DOI 
        doi = extract_doi(ocr_text)

        if doi:
            link = create_doi_link(doi)
            print(f"    ✓ DOI found: {doi}")
            print(f"      Link: {link}")
            results.append({
                "page": i + 1,
                "fileName": file_name,
                "doi": doi,
                "link": link
            })
            # break # Stop after finding the first DOI
        else:
            print(f"    ✗ No DOI found")

    # Summary
    print(f"\n{'='*60}")
    print(f"DOI EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"  Pages scanned: {total_pages}")
    print(f"  DOIs found: {len(results)}")

    for r in results:
        print(f"    Page {r['page']} ({r['fileName']}): {r['link']}")

    print(f"{'='*60}\n")

    print(json.dumps(results, indent=4))

    return results


def run_all_journals_dois(data_folder="Data"): 
    """
    Scans the Data folder and runs DOI extraction for each journal.
    Saves results to output/ and returns the list.
    """
    if not os.path.exists(data_folder):
        print(f"Data folder not found: {data_folder}")
        return []

    folders = sorted([
        f for f in os.listdir(data_folder)
        if os.path.isdir(os.path.join(data_folder, f))
    ])

    print(f"\nFound {len(folders)} journal(s) in '{data_folder}/':")

    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    results = [] 

    for i, folder in enumerate(folders, 1):
        print(f"\n[{i}/{len(folders)}] DOI Extraction: {folder}")

        folder_path = os.path.join(data_folder, folder)

        try:
            dois = extract_dois(folder_path)
            results.append({"journalName": folder, "status": "success", "dois": dois})
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({"journalName": folder, "status": "error", "dois": []})

    # Save results to output/
    output_dir = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(output_dir, exist_ok=True)

    from datetime import datetime  
    datetime_str = datetime.now().strftime("%d_%m_%Y___%H_%M")  
    output_filepath = os.path.join(output_dir, f"dois_{datetime_str}.json") 

    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print(f"\nDOI results saved to: {output_filepath}")

    return results 


if __name__ == "__main__": 


    parser = argparse.ArgumentParser(description="JournalIndexing OCR Pipeline")
    parser.add_argument(
        "journal",
        nargs="?",
        default="all",
        help='Journal folder name or path (e.g. "ajil0120no1" or "Data/ajil0120no1") or "all" to run all'
    )

    args = parser.parse_args()

    if args.journal == "all":
        run_all_journals_dois("Data")   
    else:
        # Support both "ajil0120no1" and "Data/ajil0120no1"
        journal_path = args.journal.rstrip("/")
        if not journal_path.startswith("Data"):
            journal_path = os.path.join("Data", journal_path)
        extract_dois(journal_path) 
import os
import shutil 
import time 
import json
from datetime import datetime
import argparse

# Importing necessary functions from other modules: 
from source.article_extractor import process_articles
from source.find_page_offset import get_page_offset
from source.initiateFiles import create_ocr_json, create_metadata_json, save_metadata_to_output
from source.metadata_extractor import extract_metadata
from source.scan_articles import scan_articles
from source.toc_checker import check_toc 
from source.llm import model_name
from source.toc_extractor import get_toc_pages, extract_toc_articles

def initiate_temp_files(base_folder): 

    # Clear temp folder before starting: 
    # temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
    # if os.path.exists(temp_path):
    #     shutil.rmtree(temp_path)
    # os.makedirs(temp_path, exist_ok=True)  

    # -- TEMP -- 
    # Create temp folder if not present:
    temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp") 
    os.makedirs(temp_path, exist_ok=True) 

    # Create OCR JSON file from the given base folder: 
    ocr_fp = create_ocr_json(base_folder) 

    # Create metadata JSON file from the given base folder: 
    metadata_fp = create_metadata_json(base_folder)

    return ocr_fp, metadata_fp 


def run_ocr_pipeline(base_folder):  

    print("\nOCR extraction process... \n") 

    start = time.time()

    # Initialize temp files and get their paths: 
    ocr_filepath, metadata_filepath = initiate_temp_files(base_folder)  

    # Get Page Offset: The pages before Article Page Number 1 
    page_offset = get_page_offset(ocr_filepath, useLLM = False)  
    print(f"\nEstimated page offset: {page_offset}") 

    # Extract and verify metadata: 
    metadata = extract_metadata(ocr_filepath, metadata_filepath, page_offset or 1)    # if page_offset is 0 
    # metadata = extract_metadata(ocr_filepath, metadata_filepath, page_offset)   

    # Table of Contents (ToC) checking process:
    toc_results = check_toc(ocr_filepath, base_folder, page_offset)  
    # print(json.dumps(toc_results, indent=4)) 

    # Get Page who has ToC: If not then return None 
    toc_pages = get_toc_pages(toc_results) 

    # Extracting Articles List from TOC pages: If toc_pages is None or empty, it will skip this step and return None
    if toc_pages: 
        print(f"\nTOC found on page(s): {toc_pages}") 

        # Parse True if you want to use LLM for article extraction, False for regex-based extraction
        articles = extract_toc_articles(ocr_filepath, toc_pages, base_folder, useLLM = True)   
        print(json.dumps(articles, indent=4))    

        # Use Page offset to extract article data from the correct pages. 
        process_articles(articles, page_offset, ocr_filepath, metadata_filepath)   
    else:
        print(f"\n⚠ No TOC page found.")  
        scan_articles(page_offset, ocr_filepath, metadata_filepath) 

    elapsed = round(time.time() - start, 2)
    print(f"\nTotal OCR Pipeline Time: {elapsed}s --- Model Name: {model_name}") 

    # Save to persistent output folder:
    output_filepath = save_metadata_to_output(metadata_filepath, base_folder) 
    
    return metadata, output_filepath 


def run_all_journals(data_folder="Data"):
    """
    Scans the Data folder and runs the OCR pipeline for each journal folder.
    """
    if not os.path.exists(data_folder):
        print(f"Data folder not found: {data_folder}")
        return

    folders = sorted([
        f for f in os.listdir(data_folder)
        if os.path.isdir(os.path.join(data_folder, f))
    ])

    print(f"\nFound {len(folders)} journal(s) in '{data_folder}/':")
    for i, folder in enumerate(folders, 1):
        print(f"  {i}. {folder}")

    results = {}
    timing_data = []
    total_start = time.time()

    for i, folder in enumerate(folders, 1):
        base_folder = os.path.join(data_folder, folder)
        print(f"\n{'='*60}")
        print(f"[{i}/{len(folders)}] Processing: {folder}")
        print(f"{'='*60}")

        start = time.time()

        try:
            metadata, output_filepath = run_ocr_pipeline(base_folder)
            elapsed = round(time.time() - start, 2)
            results[folder] = {"status": "success", "metadata": metadata, "output": output_filepath}
            timing_data.append({"journalName": folder, "time_s": elapsed, "status": "success"})
            print(f"  Time: {elapsed}s")
        except Exception as e:
            elapsed = round(time.time() - start, 2)
            print(f"Error processing {folder}: {e}")
            results[folder] = {"status": "error", "error": str(e)}
            timing_data.append({"journalName": folder, "time_s": elapsed, "status": "error", "error": str(e)})

    total_elapsed = round(time.time() - total_start, 2)

    # Save timing data to output/
    timing_report = {
        "total_journals": len(folders),
        "total_time_s": total_elapsed,
        "journals": timing_data
    }

    project_root = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(project_root, "output")
    os.makedirs(output_dir, exist_ok=True)

    from datetime import datetime
    datetime_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    timing_filepath = os.path.join(output_dir, f"timing_{datetime_str}.json")

    with open(timing_filepath, "w", encoding="utf-8") as f:
        json.dump(timing_report, f, indent=4, ensure_ascii=False)

    print(f"\nTiming report saved to: {timing_filepath}")

    # Final summary
    print(f"\n{'='*60}")
    print(f"BATCH SUMMARY")
    print(f"{'='*60}")
    success = sum(1 for r in results.values() if r["status"] == "success")
    print(f"  Total: {len(results)} | Success: {success} | Failed: {len(results) - success}")
    print(f"  Total time: {total_elapsed}s")

    for entry in timing_data:
        status = "✓" if entry["status"] == "success" else "✗"
        print(f"  {status} {entry['journalName']} — {entry['time_s']}s")

    return results

if __name__ == "__main__": 

    # # # Testing code for running the OCR pipeline: 
    # # run_ocr_pipeline("Data/ajil0120no1") 

    # # All journals: 
    # run_all_journals("Data") 

    parser = argparse.ArgumentParser(description="JournalIndexing OCR Pipeline")
    parser.add_argument(
        "journal",
        nargs="?",
        default="all",
        help='Journal folder name or path (e.g. "ajil0120no1" or "Data/ajil0120no1") or "all" to run all'
    )

    args = parser.parse_args()

    if args.journal == "all":
        run_all_journals("Data")
    else:
        # Support both "ajil0120no1" and "Data/ajil0120no1"
        journal_path = args.journal.rstrip("/")
        if not journal_path.startswith("Data"):
            journal_path = os.path.join("Data", journal_path)
        run_ocr_pipeline(journal_path) 
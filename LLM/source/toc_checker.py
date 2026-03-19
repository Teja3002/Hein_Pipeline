import datetime
import json     
import time
import os
import time

from source.metadata_extractor import load_json, save_json 
from source.ocr import extract_text
from source.llm import extract_toc_page, model_name 

# model_name = 'gemma3' 
# model_name = 'qwen3-vl:8b'        
# model_name = 'qwen3.5:4b'         # Preffered for best performance 
# model_name = 'qwen3.5:2b'
# model_name = 'qwen3.5:0.8b'

# if len(sys.argv) < 2:
#     print("Model name not provided. \nFollowing models are available")
#     models = ollama_list().models
#     names = [m.model for m in models] 
#     for name in names:
#         print(name)
#     sys.exit(0)

# if(len(sys.argv) < 3):
#     print("Directory name not provided. Please provide the directory containing journal folders.")
#     sys.exit(0)

# model_name = sys.argv[1]
# directory = sys.argv[2]

# print(f"Running with Model: {model_name}")

def ReturnResults(total_start, count, pages, folder_name="unknown"): 
    total_elapsed = round(time.time() - total_start, 2)

    # Save results to JSON
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(base_dir, "EVAL"), exist_ok=True)

    json_filename = f"toc_{model_name}_{folder_name}.json"  
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  
    output_path = os.path.join(project_root, "temp", json_filename) 
    # output_path = os.path.join(base_dir, "EVAL", f"toc_results_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json") 

    toc_true  = sum(1 for p in pages if p["is_toc"]) 
    toc_false = len(pages) - toc_true 

    result_data = {
        "total_pages": count,
        "total_pages_scanned": len(pages),
        "total_time_s": total_elapsed,
        "toc_found"    : toc_true,
        "toc_not_found": toc_false,
        "timestamp"  : datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
        "pages"      : pages
    }

    with open(output_path, "w") as f:
        json.dump(result_data, f, indent=2)

    return result_data 

def check_toc(ocr_filepath, folder_path, max_page_scan=15): 

    valid_extensions = ('.png', '.jpg', '.jpeg', '.tiff', '.bmp')
    png_folder = os.path.join(folder_path, "png") 
    files = [f for f in os.listdir(png_folder) if f.lower().endswith(valid_extensions)]
    # files = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)]
    files.sort() 

    total_files = len(files) 
    print(f"Found {total_files} images in folder: {os.path.basename(folder_path)}")
    
    pages = []
    total_start = time.time()
    count = 0
    is_toc_found = False
    folder_name = os.path.basename(folder_path) 

    ocr_data = load_json(ocr_filepath) 
    entries = ocr_data.get("entries", []) 

    for i, entry in enumerate(entries[:]): 

        print(f"\nScanning page {i + 1}/{total_files} - {entry.get('fileName', 'unknown')}") 

        file_path = entry.get("filePath", "")
        file_name = entry.get("fileName", "")

        ocr_text = entry.get("ocrText", "") 

        if not ocr_text:
            print(f"    Running OCR on {file_name}...")
            ocr_text = extract_text(file_path, preprocess=True)

            if not ocr_text.strip():
                print(f"    OCR returned empty text. Skipping page.")
                continue

            # Update ocrText in the entry for future use 
            entry["ocrText"] = ocr_text 

        print(f"Checking for ToC on page {i + 1}...") 

        start = time.time()
        llm_result = extract_toc_page(entry["ocrText"])   
        elapsed = round(time.time() - start, 2)

        result = llm_result.strip().upper().split()[0] 

        print(f"LLM Result: {llm_result}") 
        print("Time taken:", elapsed) 

        if(result == "YES"):
            print("TOC found on this page!")
            is_toc_found = True
            if(max_page_scan == count + 1): 
                max_page_scan += 1  
        elif(is_toc_found):
                print("TOC already found. Stopping further scans.") 
                return ReturnResults(total_start, count, pages, folder_name)     
        
        is_toc = result == "YES"

        pages.append({
            "page"    : i + 1,
            "file"    : file_name,
            "is_toc"  : is_toc,
            "response": llm_result, 
            "time_s"  : elapsed
        })

        save_json(ocr_filepath, ocr_data)

        count += 1 

        if count >= max_page_scan:  # Limit to first 10 pages for testing 
            return ReturnResults(total_start, count, pages, folder_name) 


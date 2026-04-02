import yaml

from source.llm import get_page_number
from source.ocr import extract_text
from source.toc_extractor import load_json, save_json 



def get_last_native_page(structure_path): 
    """
    Reads structure.yml and returns the native page number of the last entry.

    Args:
        structure_path: Path to structure.yml

    Returns:
        int or str: The native page number of the last entry, or None on failure
    """
    with open(structure_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) 

    pages = data.get("pages", [])

    if not pages:
        print("No pages found in structure.yml")
        return None

    last_native = pages[-1].get("native")
    print(f"  Last page native: {last_native}")

    return last_native
    

def get_page_offset(ocr_filepath, useLLM = False): 
    """
    Calculates the offset between file position and printed page number.
    
    Logic:
      1. Get total pages from ocrData JSON
      2. OCR the last page and ask LLM for its printed page number
      3. offset = total_pages - last_page_number

    Other functions use this as: file_position = offset + printed_page_number

    Returns:
        int: The page offset, or None on failure
    """

    ocr_data = load_json(ocr_filepath)
    entries = ocr_data.get("entries", [])
    total_pages = len(entries)

    if total_pages == 0:
        print("No pages found in ocrData.")
        return None

    # Get OCR text of the last page 
    last_entry = entries[-1]  
    ocr_text = last_entry.get("ocrText", "")

    if not ocr_text: 
        print(f"  Running OCR on last page ({last_entry.get('fileName', '')})...")
        ocr_text = extract_text(last_entry.get("filePath", ""), preprocess=True)

        if not ocr_text.strip():
            print("  OCR returned empty text for last page.")
            return None

        last_entry["ocrText"] = ocr_text

    save_json(ocr_filepath, ocr_data) 

    if(useLLM): 
        print("Asking LLM for printed page number of the last page...") 
        llm_response = get_page_number(ocr_text, image_path=last_entry.get("filePath")) 

        try: 
            last_page_number = int(llm_response.strip()) 
        except ValueError: 
            print(f"  LLM returned non-numeric response: '{llm_response}'") 
            return None 
    else: 
        print("Getting last page number from structure.yml...") 
        last_page_number = get_last_native_page(ocr_data.get("structurePath"))  


    offset = total_pages - last_page_number

    print(f"  Total files: {total_pages}")
    print(f"  Last page number: {last_page_number}")
    print(f"  Page offset: {offset}")

    return offset 
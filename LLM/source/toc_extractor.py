import os
import re
import json

from .llm import safe_model_name, get_article_page_numbers 
from .metadata_extractor import load_json, save_json  

# def load_json(filepath):
#     """Load and return a JSON file."""
#     with open(filepath, "r", encoding="utf-8") as f:
#         return json.load(f)

# def save_json(filepath, data):
#     """Save data to a JSON file."""
#     with open(filepath, "w", encoding="utf-8") as f:
#         json.dump(data, f, indent=4, ensure_ascii=False)

# -------- Get TOC Pages --------

def get_toc_pages(toc_results):
    """
    Returns consecutive TOC page numbers starting from the first one found.
    If no TOC found, returns None.
    """
    pages = toc_results.get("pages", [])
    toc_pages = []
    found_first = False

    for page in pages:
        if page.get("is_toc"):
            found_first = True
            toc_pages.append(page["page"])
        elif found_first:
            break

    return toc_pages if toc_pages else None


# -------- TOC Parsing Helpers --------

def strip_sidebar(line: str) -> str:
    """Strip second-column/sidebar text after a large whitespace gap."""
    parts = re.split(r'\s{8,}', line.strip())
    if len(parts) < 2:
        return parts[0]
    rightmost = parts[-1].strip()
    if re.match(r'^\d+$', rightmost):
        return line.strip()
    return parts[0]


def is_year(n: int) -> bool:
    """4-digit numbers 1000-2099 are almost certainly years, not page numbers."""
    return 1000 <= n <= 2099


END_OF_LINE_NUM = re.compile(r'^(.*?)\s+(\d+)\s*$')
MAX_PAGE = 999   # Filter out unreasonably high page numbers that are likely OCR errors


# -------- Extract TOC Entries --------

def extract_toc_entries(ocr_text):
    """
    Parse OCR text from known TOC pages and return list of {id, page} dicts.
    Since we already know these are TOC pages, we parse all lines directly.
    """
    lines = ocr_text.splitlines()

    entries = []
    last_page_num = -1
    pending_text_parts = []
    last_entry_line = None
    MAX_ENTRY_GAP = 30 

    for line_idx, line in enumerate(lines):
        stripped = strip_sidebar(line).strip()
        if not stripped:
            continue

        m = END_OF_LINE_NUM.match(stripped)

        if m:
            text_part = m.group(1).strip()
            candidate_num = int(m.group(2))

            # Skip years
            if is_year(candidate_num):
                pending_text_parts.append(stripped)
                continue

            # Skip if exceeds max page
            if candidate_num > MAX_PAGE:
                pending_text_parts.append(stripped)
                continue

            # Must be strictly increasing
            if candidate_num <= last_page_num:
                pending_text_parts.append(stripped)
                continue

            # Preceding word signals non-page context
            words_before = text_part.split()
            preceding = words_before[-1].rstrip('.').lower() if words_before else ''
            if preceding in ('no.', 'vol', 'number', 'figure', 'fig', 'table', 'part',
                             'chapter', 'art', 'article', 'section', 'sec', 'para'):
                # Vol./No./Number are journal metadata — clear any accumulated header text
                if preceding in ('no', 'vol', 'number'):
                    continue 
                else:
                    pending_text_parts.append(stripped)

            # Number preceded by comma or period is likely a citation
            if text_part.endswith(',') or text_part.endswith('.'):
                pending_text_parts.append(stripped)
                continue

            # Valid — commit entry
            pending_text_parts.append(text_part)
            full_id = ' '.join(pending_text_parts).strip()

            # Skip unreasonably long entries (OCR garbage)
            if len(full_id.split()) > 250:
                last_page_num = candidate_num
                pending_text_parts = []
                continue

            # If gap from last entry is too large, reset
            if last_entry_line is not None and (line_idx - last_entry_line) > MAX_ENTRY_GAP:
                entries = []
                last_page_num = candidate_num
                pending_text_parts = []
                last_entry_line = None
                continue

            entries.append({
                "id": full_id,
                "page": candidate_num
            })

            last_page_num = candidate_num
            last_entry_line = line_idx
            pending_text_parts = []

        else:
            pending_text_parts.append(stripped)

    return entries


# -------- Main Function --------

def extract_toc_articles(ocr_filepath, toc_page_numbers, folder_path, useLLM = True):
    """
    Reads stored OCR text from ocrData JSON for the TOC pages
    and extracts article names with page numbers.

    Args:
        ocr_filepath: Path to ocrData JSON file
        toc_page_numbers: List of page numbers that have TOC (e.g. [1, 2])

    Returns:
        list of dicts with article id and page, or None if no entries found
    """

    ocr_data = load_json(ocr_filepath) 
    entries = ocr_data.get("entries", [])

    # Combine OCR text from TOC pages (already stored)
    combined_ocr = ""

    for page_num in toc_page_numbers:
        idx = page_num - 1
        if idx < 0 or idx >= len(entries):
            print(f"  NO Page {page_num} out of range. Skipping.")
            continue

        ocr_text = entries[idx].get("ocrText", "")
        if ocr_text.strip():
            combined_ocr += ocr_text + "\n"
            print(f"  OK Loaded OCR for page {page_num} ({entries[idx].get('fileName', '')})")
        else:
            print(f"  NO No OCR text stored for page {page_num}")

    if not combined_ocr.strip():
        print("No OCR text found for TOC pages.")
        return None 
    
    # Use LLM toggle 
    if(useLLM): 
        print("\nExtracting articles using LLM...") 

        # Use first TOC page image for vision input
        first_toc_idx = toc_page_numbers[0] - 1
        first_toc_image = entries[first_toc_idx].get("filePath") if 0 <= first_toc_idx < len(entries) else None

        articles = get_article_page_numbers(combined_ocr, image_path=first_toc_image)  
        try:
            articles = json.loads(articles) 
            if not isinstance(articles, list):
                print("  LLM response is not a list. Returning empty.")
                print("LLM raw response:", articles)
                articles = []
        except (json.JSONDecodeError, TypeError):
            print(f"  Failed to parse LLM response as JSON. Returning empty.")
            articles = [] 
    else: 
        # Extract TOC entries from combined text 
        articles = extract_toc_entries(combined_ocr) 

    if not articles:
        print("  No articles found in TOC.")
        return None

    print(f"\n  Found {len(articles)} articles:")
    for e in articles:
        print(f"    {e['id'][:60]}... -> page {e['page']}")

    # Saving the article files before returning it 

    folder_name = os.path.basename(folder_path)  

    if(useLLM): 
        json_filename = f"articles_{safe_model_name}_{folder_name}.json"
    else:
        json_filename = f"articles_{folder_name}.json"  

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  
    output_path = os.path.join(project_root, "temp", json_filename)  

    save_json(ocr_filepath, ocr_data) 

    with open(output_path, "w") as f: 
        json.dump(articles, f, indent=2)

    return articles


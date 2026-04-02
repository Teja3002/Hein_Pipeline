import json
from .metadata_extractor import load_json, save_json 
from .ocr import extract_text
from .llm import is_new_article, extract_article_fields
from .article_extractor import extract_article_doi, get_external_link
from .verifier.verify_article_title import verify_article_title


# def load_json(filepath):
#     with open(filepath, "r", encoding="utf-8") as f:
#         return json.load(f)


# def save_json(filepath, data):
#     with open(filepath, "w", encoding="utf-8") as f:
#         json.dump(data, f, indent=4, ensure_ascii=False)


def scan_articles(page_offset, ocr_filepath, metadata_filepath, issue_key="-1"):
    """
    Sequentially scans pages to detect article boundaries
    when no TOC is available.

    1. Start from first article page (offset + 1)
    2. For each page, ask LLM: "Is this the start of a new article?"
    3. When a new article is detected, extract title/authors from that page
    4. Previous article's end page = current page - 1
    5. Extract DOI for each detected article
    """

    ocr_data = load_json(ocr_filepath)
    entries = ocr_data.get("entries", [])
    total_pages = ocr_data.get("totalPages", len(entries))

    metadata = load_json(metadata_filepath)
    # metadata["articles"] = []

    start_index = page_offset  # 0-based index for first article page
    article_boundaries = []    # List of page indices where new articles start

    print(f"\n{'='*60}")
    print(f"Sequential Article Scan (No TOC)")
    print(f"Starting from file position: {start_index + 1}")
    print(f"Total pages to scan: {total_pages - start_index}")
    print(f"{'='*60}\n")

    # Phase 1: Detect article boundaries
    print("Phase 1: Detecting article boundaries...\n")

    for i in range(start_index, total_pages):
        entry = entries[i]
        file_name = entry.get("fileName", "")
        ocr_text = entry.get("ocrText", "")

        if not ocr_text:
            print(f"  Running OCR on {file_name}...")
            ocr_text = extract_text(entry.get("filePath", ""), preprocess=True)

            if not ocr_text.strip():
                continue

            entry["ocrText"] = ocr_text

        # Ask LLM if this is the start of a new article
        result = is_new_article(ocr_text, image_path=entry.get("filePath"))  

        if result: 
            article_boundaries.append(i)
            print(f"  OK New article detected at page {i + 1} ({file_name})")
        else:
            print(f"  - Page {i + 1} ({file_name}) — continuation")

    save_json(ocr_filepath, ocr_data)

    if not article_boundaries:
        print("\n  WARN No articles detected.")
        return metadata

    print(f"\n  Detected {len(article_boundaries)} article(s)")

    # Phase 1.5: Verify boundaries — only keep pages where a valid title is found
    verified_boundaries = []

    for boundary in article_boundaries:
        ocr_text = entries[boundary].get("ocrText", "")
        extracted, raw = extract_article_fields(ocr_text, image_path=entries[boundary].get("filePath"))  

        title_valid, _ = verify_article_title(extracted.get("title")) 

        if title_valid:
            verified_boundaries.append(boundary)
            print(f"  OK Page {boundary + 1} verified as article start")
        else:
            print(f"  NO Page {boundary + 1} filtered out (no valid title)")

    article_boundaries = verified_boundaries 
    print(f"\n  Verified {len(article_boundaries)} article(s)")

    # Phase 2: Extract data for each article 
    print(f"\nPhase 2: Extracting article data...\n")

    for i, start_idx in enumerate(article_boundaries):
        # End page is next article start - 1, or last page
        if i < len(article_boundaries) - 1:
            end_idx = article_boundaries[i + 1] - 1
        else:
            end_idx = total_pages - 1

        start_page = start_idx + 1  # 1-based
        end_page = end_idx + 1      # 1-based
        native_page = str(start_page - page_offset) 

        print(f"\n  [{i + 1}/{len(article_boundaries)}] Pages: {start_page} - {end_page}")

        # Extract title and authors from first page of article 
        ocr_text = entries[start_idx].get("ocrText", "")
        extracted, raw = extract_article_fields(ocr_text, image_path=entries[start_idx].get("filePath"))
        print(f"    Title: {extracted.get('title', 'N/A')}")

        # Extract DOI
        doi_result = extract_article_doi(start_page, end_page, ocr_filepath) 

        external_link = None
        if doi_result:
            external_link = get_external_link(doi_result["link"])

        metadata["pages"].append({
            "id": i + 1,
            "native": native_page 
        })

        section = {
            # "page": native_page,
            # "startFile": start_page, 
            # "endFile": end_page, 
            "title": extracted.get("title", ""), 
            "citation": "",
            "description": "",
            "doi": doi_result.get("doi", "") if doi_result else "",
            "external_url": external_link or "",
            "authors": extracted.get("authors", []) or [], 
            "issue": issue_key
        }

        metadata["sections"][str(i + 1)] = section

    save_json(metadata_filepath, metadata)
    print(f"\n  {len(article_boundaries)} articles saved to: {metadata_filepath}")

    return metadata

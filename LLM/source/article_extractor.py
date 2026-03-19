import os
import json
import re 
import requests

from source.metadata_extractor import load_json, save_json
from source.ocr import extract_text
from source.llm import extract_article_fields
from source.verifier.verify_article_title import verify_article_title
from source.verifier.verify_article_authors import verify_article_authors

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


def get_external_link(doi_link):
    """
    Follows a DOI link redirect and returns the final URL.

    Args:
        doi_link: DOI URL (e.g. "https://doi.org/10.1017/ajil.2025.10129")

    Returns:
        str: The final redirected URL, or None if it fails
    """
    if not doi_link:
        return None

    try:
        response = requests.head(doi_link, allow_redirects=True, timeout=10)
        if response.status_code == 200:
            print(f"      OK External link: {response.url}")
            return response.url 
        else:
            print(f"      NO External link failed (status {response.status_code})")
            return None
    except requests.RequestException as e: 
        print(f"      NO External link error: {e}")
        return None


def extract_article_doi(start_page, end_page, ocr_filepath):
    """
    Extracts DOI from an article's pages. Stops at first DOI found.

    Args:
        start_page: File position where the article starts (1-based)
        end_page: File position where the article ends (1-based)
        ocr_filepath: Path to ocrData JSON

    Returns:
        dict with doi and link, or None if no DOI found
    """

    ocr_data = load_json(ocr_filepath)
    entries = ocr_data.get("entries", [])

    for i in range(start_page - 1, end_page):
        if i < 0 or i >= len(entries):
            continue

        entry = entries[i]
        file_name = entry.get("fileName", "")
        ocr_text = entry.get("ocrText", "")

        if not ocr_text:
            print(f"      Running OCR on {file_name}...")
            ocr_text = extract_text(entry.get("filePath", ""), preprocess=True)

            if not ocr_text.strip():
                continue

            entry["ocrText"] = ocr_text

        doi = extract_doi(ocr_text)

        if doi:
            link = create_doi_link(doi)
            print(f"      OK DOI found on {file_name}: {doi}")
            save_json(ocr_filepath, ocr_data)
            return {"doi": doi, "link": link}

    save_json(ocr_filepath, ocr_data)
    print(f"      NO DOI found in pages {start_page}-{end_page}")
    return None


def extract_article_info(start_page, end_page, ocr_filepath):
    """
    Extracts title and authors from an article's pages.

    Scans the first few pages of the article, runs OCR if needed,
    and uses LLM to extract title and authors. Verifies both fields.

    Args:
        start_page: File position where the article starts (1-based)
        end_page: File position where the article ends (1-based)
        ocr_filepath: Path to ocrData JSON

    Returns:
        dict with title, authors, or empty values if extraction fails
    """

    ocr_data = load_json(ocr_filepath)
    entries = ocr_data.get("entries", [])

    # Only scan first few pages of the article 
    pages_to_scan = end_page - start_page + 1 

    result = {
        "title": None,
        "authors": None
    }

    for i in range(pages_to_scan):
        page_idx = start_page - 1 + i 

        if page_idx < 0 or page_idx >= len(entries):
            continue

        entry = entries[page_idx]
        file_name = entry.get("fileName", "")
        ocr_text = entry.get("ocrText", "")

        # Run OCR if not already stored
        if not ocr_text:
            print(f"      Running OCR on {file_name}...")
            ocr_text = extract_text(entry.get("filePath", ""), preprocess=True)

            if not ocr_text.strip():
                print(f"      OCR returned empty text. Skipping.")
                continue

            entry["ocrText"] = ocr_text

        # Call LLM to extract title and authors
        print(f"      Extracting from {file_name}...")
        extracted, raw = extract_article_fields(ocr_text)
        print(f"      LLM raw: {raw}")

        # Verify title
        if result["title"] is None:
            title_value = extracted.get("title")
            is_valid, reason = verify_article_title(title_value)
            if is_valid:
                result["title"] = title_value
                print(f"      OK title = \"{title_value}\"")
            else:
                print(f"      NO title: {reason}")

        # Verify authors
        if result["authors"] is None:
            authors_value = extracted.get("authors")
            is_valid, reason = verify_article_authors(authors_value)
            if is_valid:
                result["authors"] = authors_value
                print(f"      OK authors = {authors_value}")
            else:
                print(f"      NO authors: {reason}")

        # Stop if both fields are verified
        if result["title"] and result["authors"]:
            break

    # Save updated ocrData with any new OCR text
    save_json(ocr_filepath, ocr_data)

    return result 

    

def process_articles(articles, page_offset, ocr_filepath, metadata_filepath): 
    """
    Loops through all articles, extracts title and authors for each,
    and saves results to metadata JSON.

    Args:
        articles: List of dicts with 'id' and 'page' from TOC extraction
        page_offset: Offset to convert printed page to file position
        ocr_filepath: Path to ocrData JSON
        metadata_filepath: Path to metadata JSON
        total_pages: Total number of pages in the journal
    """
    ocr_data = load_json(ocr_filepath) 
    total_pages = ocr_data.get("totalPages") 

    metadata = load_json(metadata_filepath) 
    metadata["articles"] = []

    for i, article in enumerate(articles):
        start_page = int(article["page"]) + page_offset

        if i < len(articles) - 1:
            end_page = int(articles[i + 1]["page"]) + page_offset - 1 
        else:
            end_page = total_pages

        print(f"\n  [{i + 1}/{len(articles)}] {article['id'][:60]}...")
        print(f"    Pages: {start_page} - {end_page}")

        result = extract_article_info(start_page, end_page, ocr_filepath)
        doi_result = extract_article_doi(start_page, end_page, ocr_filepath)

        external_link = None
        if doi_result:
            external_link = get_external_link(doi_result["link"])

        # metadata["articles"].append({ 
        #     "page": article["page"],
        #     "startFile": start_page,
        #     "endFile": end_page, 
        #     "title": result.get("title"),
        #     "authors": result.get("authors"), 
        #     "doi": doi_result.get("doi") if doi_result else None, 
        #     "link": doi_result.get("link") if doi_result else None, 
        #     "external_link": external_link 
        # })

        section = {
            "page": article["page"],
            "startFile": start_page, 
            "endFile": end_page, 
            "title": result.get("title", ""), 
            "citation": "",
            "description": "",
            "doi": doi_result.get("doi", "") if doi_result else "",
            "external_url": external_link or "",
            "authors": result.get("authors", []) or [] 
        }

        metadata["sections"][str(i + 1)] = section

        

    save_json(metadata_filepath, metadata)  

    print(f"\n  {len(articles)} articles saved to: {metadata_filepath}")

    return "complete"  

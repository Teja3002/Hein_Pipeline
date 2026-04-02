import os
import json

from source.ocr import extract_text 
from source.llm import extract_metadata_fields
from source.verifier.verify_volume import verify_volume
from source.verifier.verify_date import verify_date
from source.verifier.verify_title import verify_title
from source.verifier.verify_issue import verify_issue
from source.verifier.verify_issn import verify_issn
from source.verifier.verify_eissn import verify_eissn

# Field descriptions passed to the LLM (only pending ones are sent)
# FIELD_DESCRIPTIONS = {
#     "volume": 'The volume number (e.g. "89")',
#     "date": 'The publication date (e.g. "January 2026")',
#     "title": 'The full journal title (e.g. "The Modern Law Review")',
#     "issue_number": 'The issue number (e.g. "1")',
#     "issn": 'The print ISSN (e.g. "0002-9300")',
#     "eissn": 'The electronic E-ISSN (e.g. "2161-7953")',
# }

# FIELD_DESCRIPTIONS = {
#     "volume": 'The volume number (e.g. "89")',
#     "date": 'The publication date (e.g. "January 2026")',
#     "title": 'The full journal title (e.g. "The Modern Law Review")', 
#     "issue": 'The issue number (e.g. "1")' 
# }

FIELD_DESCRIPTIONS = {
    "volume": 'The volume number (e.g. "89"). May appear as "VOLUME 143"',
    "date":   'The publication date (e.g. "January 2026")',
    "title":  'The full journal title (e.g. "The Modern Law Review")',
    "issue":  'The issue number (e.g. "1"). May appear as "NUMBER 1" or "No. 1" or "Issue 1"',
}

# Verifier for each field
FIELD_VERIFIERS = {
    "volume": verify_volume,
    "date": verify_date,
    "title": verify_title,
    "issue": verify_issue,
    "issn": verify_issn,
    "eissn": verify_eissn,
}


def load_json(filepath):
    """Load and return a JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f) 


def save_json(filepath, data):
    """Save data to a JSON file."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def extract_metadata(ocr_filepath, metadata_filepath, MAX_PAGES=10):
    """
    Iterates through pages in ocrData JSON, extracts metadata fields
    via a single LLM call per page (only requesting pending fields),
    verifies them, and updates the metadata JSON.

    Stops when all required fields are verified or MAX_PAGES is reached.

    Args:
        ocr_filepath: Path to ocrData_{journalName}_{dateTime}.json
        metadata_filepath: Path to metadata_{journalName}.json

    Returns:
        dict: The updated metadata.
    """

    ocr_data = load_json(ocr_filepath)
    metadata = load_json(metadata_filepath)
    entries = ocr_data.get("entries", [])

    # Track which fields have been successfully verified
    verified_fields = {}
    pending_fields = set(FIELD_DESCRIPTIONS.keys()) 

    # Limit total pages to scan to avoid long runtimes, as currently this is development code and we want quick iterations.
    # total_pages = min(len(entries), MAX_PAGES) 
    total_pages = MAX_PAGES 

    print(f"\n{'='*60}") 
    print(f"Metadata Extraction - {ocr_data.get('journalName', 'Unknown')}")
    print(f"Pages available: {len(entries)} | Will scan up to: {total_pages}")
    print(f"Fields to extract: {', '.join(pending_fields)}") 
    print(f"{'='*60}\n")

    for i, entry in enumerate(entries[:MAX_PAGES]):

        # Stop if all fields are verified
        if not pending_fields:
            print(f"\nAll required fields verified! Stopped at page {i}.") 
            break

        file_path = entry.get("filePath", "")
        file_name = entry.get("fileName", "")

        print(f"\n--- Page {i + 1}/{total_pages} ({file_name}) ---")
        print(f"    Remaining fields: {', '.join(pending_fields)}")

        # Get OCR text for this page
        ocr_text = entry.get("ocrText", "")

        # If ocrText is empty, run OCR on the image
        if not ocr_text:
            print(f"    Running OCR on {file_name}...")
            ocr_text = extract_text(file_path, preprocess=True)

            if not ocr_text.strip():
                print(f"    OCR returned empty text. Skipping page.")
                continue

            # Update ocrText in the entry for future use
            entry["ocrText"] = ocr_text

        # Build pending fields dict with only what we still need
        pending_descriptions = {
            key: FIELD_DESCRIPTIONS[key] for key in pending_fields
        }

        # Single LLM call for all pending fields
        print(f"    Calling LLM for: {', '.join(pending_fields)}...")
        result, raw_response = extract_metadata_fields(ocr_text, pending_descriptions, image_path=file_path)
        print(f"    LLM raw: {raw_response}") 

        # Verify each returned field
        fields_to_remove = []

        for field_name in list(pending_fields):
            value = result.get(field_name)
            verifier = FIELD_VERIFIERS[field_name]
            is_valid, reason = verifier(value) 

            if is_valid:
                verified_fields[field_name] = value
                fields_to_remove.append(field_name) 
                print(f"    OK {field_name} = \"{value}\" ({reason})")
            else:
                print(f"    NO {field_name}: {reason}")

        # Remove verified fields from pending set
        for field_name in fields_to_remove:
            pending_fields.discard(field_name)

    # Update metadata JSON with verified fields
    for field_name, value in verified_fields.items():
        if field_name == "date":
            issue_key = str(verified_fields.get("issue", "-1"))
            metadata["issue_date"][issue_key] = value
        elif field_name == "issue":
            # Store as list — append if not already present
            if not isinstance(metadata["issue"], list):
                metadata["issue"] = []
            issue_str = str(value)
            if issue_str not in metadata["issue"]:
                metadata["issue"].append(issue_str)
        else:
            metadata[field_name] = value

    save_json(metadata_filepath, metadata)

    # Also save updated ocrData (with ocrText filled in for scanned pages)
    save_json(ocr_filepath, ocr_data)

    # Summary
    print(f"\n{'='*60}")
    print(f"EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"  Verified: {len(verified_fields)}/{len(FIELD_DESCRIPTIONS)}")

    for field_name in FIELD_DESCRIPTIONS:
        if field_name in verified_fields:
            print(f"    OK {field_name}: \"{verified_fields[field_name]}\"")
        else:
            print(f"    NO {field_name}: NOT FOUND")

    if pending_fields:
        print(f"\n  WARN Missing after {total_pages} pages: {', '.join(pending_fields)}")

    print(f"\n  Metadata saved to: {metadata_filepath}")
    print(f"{'='*60}\n")

    return metadata


if __name__ == "__main__":
    import glob

    temp_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp") 

    ocr_files = glob.glob(os.path.join(temp_path, "ocrData_*.json"))
    meta_files = glob.glob(os.path.join(temp_path, "metadata_*.json"))

    if ocr_files and meta_files:
        extract_metadata(ocr_files[0], meta_files[0])
    else:
        print("No temp files found. Run ocr_pipeline.py first.")  
